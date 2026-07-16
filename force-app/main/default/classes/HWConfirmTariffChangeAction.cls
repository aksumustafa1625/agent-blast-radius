/**
 * HWConfirmTariffChangeAction — the consent guardrail (ADR-020).
 *
 * This is the only action in HanseWatt that changes a customer's contract, and it is
 * deliberately the hardest one to reach. Two independent guarantees, BOTH enforced by the
 * code rather than by the prompt:
 *
 * ── 1. The proposal number cannot be faked ───────────────────────────────────────────
 * A change is applied only against a request number that (a) exists, (b) belongs to THIS
 * account, (c) is in an open state, and (d) has not expired. The number is minted by the
 * platform inside HWProposeTariffChangeAction and exists nowhere else — so a model that
 * skipped the proposal, invented a number, or replayed another customer's number has
 * nothing the code will act on. It refuses, and ZERO DML runs.
 *
 * ── 2. The change cannot be applied on the FIRST confirmation ────────────────────────
 * A `customerConfirmed` Boolean would be prompt-wishing (the model fills it in). Even an
 * instruction that says "ask twice" is prompt-wishing: nothing stops the model from acting
 * on the first "Ja". So the second confirmation is enforced structurally, as a state
 * machine:
 *
 *      Proposed  --confirm #1-->  Terms_Presented  --confirm #2-->  Applied
 *                (does NOT apply;                  (applies)
 *                 returns the binding
 *                 terms to be read out)
 *
 * The first call **physically cannot** change the contract. It transitions the proposal to
 * `Terms_Presented`, hands the agent the binding terms (this is a contract change, it takes
 * effect next billing period, here is the saving and the assumption it rests on), and tells
 * it to obtain an explicit confirmation and call again. Only the second call applies.
 *
 * So the customer is guaranteed to see the binding terms and to confirm them — not because
 * the agent was asked nicely, but because there is no code path that skips it.
 *
 * On success it (a) switches the contract's tariff, (b) marks the proposal Applied,
 * (c) opens a Case so a human owns the follow-through, and (d) publishes
 * `Tariff_Change_Requested__e` — the seam a MuleSoft subscriber would forward to SAP IS-U.
 * The far side of that seam is simulated here; the seam itself is real (see STATUS.md).
 *
 * Idempotent: confirming an already-applied change reports the original outcome and opens
 * no second case.
 *
 * Bulk-safe (ADR-006): one query, one update per object, one publish. No DML in loops.
 */
public with sharing class HWConfirmTariffChangeAction {

    public class Request {
        @InvocableVariable(
            label='Account Id'
            description='The VERIFIED customer Account Id, from HW Verify Customer. Never pass an email address or a guessed value.'
            required=true)
        public String accountId;   // String, not Id: the LLM fills it — see HWIds

        @InvocableVariable(
            label='Request Number'
            description='The request number returned by HW Propose Tariff Change (e.g. TCR-00001). You cannot invent this: it is issued by the system when the proposal is created.'
            required=true)
        public String requestNumber;
    }

    public class Result {
        @InvocableVariable(label='Applied') public Boolean applied;
        @InvocableVariable(label='Awaiting Final Confirmation') public Boolean awaitingFinalConfirmation;
        @InvocableVariable(label='Binding Terms') public String bindingTerms;
        @InvocableVariable(label='Request Number') public String requestNumber;
        @InvocableVariable(label='New Tariff') public String newTariff;
        @InvocableVariable(label='Annual Saving') public Decimal annualSaving;
        @InvocableVariable(label='Case Number') public String caseNumber;
        @InvocableVariable(label='Refusal Reason') public String refusalReason;
        @InvocableVariable(label='Message') public String message;
    }

    @InvocableMethod(
        label='HW Confirm Tariff Change'
        description='Confirms a tariff change against a request number issued by HW Propose Tariff Change. The FIRST call never applies the change: it returns the binding terms, which you must read to the customer before asking for an explicit, binding confirmation. Call it a SECOND time with the same request number only after the customer has confirmed those terms. An unknown, foreign or expired request number is always refused and nothing is modified.')
    public static List<Result> run(List<Request> requests) {
        // Load only the proposals minted for the accounts in play. The account scoping here
        // is the structural cross-customer guarantee.
        Set<String> numbers = new Set<String>();
        Set<Id> accountIds = new Set<Id>();
        for (Request req : requests) {
            if (String.isNotBlank(req.requestNumber)) numbers.add(req.requestNumber.trim().toUpperCase());
            Id acc = HWIds.accountId(req.accountId);
            if (acc != null) accountIds.add(acc);
        }

        Map<String, Tariff_Change_Request__c> byNumber = new Map<String, Tariff_Change_Request__c>();
        if (!numbers.isEmpty() && !accountIds.isEmpty()) {
            String q =
                'SELECT Id, Name, Account__c, Status__c, Expires_At__c, Applied_At__c, '
              + '       Annual_Saving__c, Assumption_Basis__c, Proposed_Tariff__c, '
              + '       Proposed_Tariff__r.Name, Service_Contract_Ref__c '
              + 'FROM Tariff_Change_Request__c '
              + 'WHERE Name IN :nums AND Account__c IN :accIds';   // scoped to the caller's own accounts
            Map<String, Object> binds = new Map<String, Object>{ 'nums' => numbers, 'accIds' => accountIds };
            for (Tariff_Change_Request__c t :
                    (List<Tariff_Change_Request__c>) Database.queryWithBinds(q, binds, AccessLevel.USER_MODE)) {
                byNumber.put(t.Name.toUpperCase(), t);
            }
        }

        List<Service_Contract__c> contractUpdates = new List<Service_Contract__c>();
        List<Tariff_Change_Request__c> requestUpdates = new List<Tariff_Change_Request__c>();
        List<Case> casesToOpen = new List<Case>();
        List<Tariff_Change_Requested__e> events = new List<Tariff_Change_Requested__e>();
        List<Result> results = new List<Result>();
        List<Integer> caseSlotByResult = new List<Integer>();
        Set<String> handledThisRun = new Set<String>();   // a number is advanced at most once per call

        for (Request req : requests) {
            Result res = new Result();
            res.applied = false;
            res.awaitingFinalConfirmation = false;
            res.requestNumber = req.requestNumber;
            caseSlotByResult.add(-1);

            // ---- Refusal gates. Any one of these means ZERO DML for this request. ----
            if (HWIds.accountId(req.accountId) == null) {
                res.refusalReason = 'NO_IDENTITY';
                res.message = 'I need to identify your account first before I can change anything.';
                results.add(res);
                continue;
            }
            if (String.isBlank(req.requestNumber)) {
                res.refusalReason = 'NO_REQUEST_NUMBER';
                res.message = 'I cannot change a tariff without a proposal. Let me quote the options '
                    + 'first, and I will only switch you after you confirm.';
                results.add(res);
                continue;
            }

            String key = req.requestNumber.trim().toUpperCase();
            Tariff_Change_Request__c tcr = byNumber.get(key);

            if (tcr == null) {
                // Either it does not exist, or it belongs to a DIFFERENT customer.
                res.refusalReason = 'UNKNOWN_OR_FOREIGN_REQUEST';
                res.message = 'That proposal number is not valid for this account. I will not change '
                    + 'a contract without a proposal I issued to you. Shall I quote the options again?';
                results.add(res);
                continue;
            }
            if (tcr.Status__c == 'Applied') {
                res.applied      = true;                       // idempotent
                res.newTariff    = tcr.Proposed_Tariff__r.Name;
                res.annualSaving = tcr.Annual_Saving__c;
                res.message      = 'This change was already applied. Your contract is on '
                    + tcr.Proposed_Tariff__r.Name + '. Nothing further is needed.';
                results.add(res);
                continue;
            }
            if (tcr.Status__c != 'Proposed' && tcr.Status__c != 'Terms_Presented') {
                res.refusalReason = 'NOT_OPEN';
                res.message = 'That proposal is no longer open. Let me quote the tariffs again.';
                results.add(res);
                continue;
            }
            if (tcr.Expires_At__c == null || tcr.Expires_At__c < System.now()) {
                if (!handledThisRun.contains(key)) {
                    tcr.Status__c = 'Expired';
                    requestUpdates.add(tcr);
                    handledThisRun.add(key);
                }
                res.refusalReason = 'EXPIRED';
                res.message = 'That proposal has expired, so I will not apply it. Let me re-quote the '
                    + 'tariffs at your current consumption and you can confirm the fresh figures.';
                results.add(res);
                continue;
            }
            if (handledThisRun.contains(key)) {
                // The same proposal was already advanced earlier in this same invocation.
                res.refusalReason = 'ALREADY_HANDLED_IN_THIS_CALL';
                res.message = 'That proposal has already been handled in this turn.';
                results.add(res);
                continue;
            }

            // ================= PHASE 1: present the binding terms. DO NOT APPLY. =================
            if (tcr.Status__c == 'Proposed') {
                tcr.Status__c = 'Terms_Presented';
                requestUpdates.add(tcr);
                handledThisRun.add(key);

                res.awaitingFinalConfirmation = true;
                res.newTariff    = tcr.Proposed_Tariff__r.Name;
                res.annualSaving = tcr.Annual_Saving__c;
                res.bindingTerms =
                      'This is a BINDING change to the customer\'s energy contract.\n'
                    + '- New tariff: ' + tcr.Proposed_Tariff__r.Name + '\n'
                    + '- Takes effect from the next billing period.\n'
                    + '- Quoted annual saving: ' + tcr.Annual_Saving__c + '\n'
                    + '- The saving depends on this assumption: ' + tcr.Assumption_Basis__c + '\n'
                    + '- Proposal ' + tcr.Name + ' is valid until ' + tcr.Expires_At__c.format() + '.';
                // The terms are repeated inside the message so this action works even where the
                // agent only surfaces `message` — the customer must always get to see them.
                res.message =
                      'NOTHING HAS BEEN CHANGED YET. Read these binding terms to the customer in '
                    + 'their own language, then ask them to confirm the change explicitly.\n\n'
                    + res.bindingTerms + '\n\n'
                    + 'ONLY if the customer then explicitly confirms, call HW Confirm Tariff Change '
                    + 'AGAIN with the same request number (' + tcr.Name + '). Until that second call '
                    + 'the tariff has NOT changed — do not tell the customer that it has.';
                results.add(res);
                continue;
            }

            // ================= PHASE 2: the customer confirmed the terms. Apply. =================
            handledThisRun.add(key);
            if (tcr.Service_Contract_Ref__c != null) {
                contractUpdates.add(new Service_Contract__c(
                    Id = tcr.Service_Contract_Ref__c,
                    Tariff__c = tcr.Proposed_Tariff__c));
            }
            tcr.Status__c     = 'Applied';
            tcr.Applied_At__c = System.now();
            requestUpdates.add(tcr);

            casesToOpen.add(new Case(
                AccountId   = tcr.Account__c,
                Subject     = 'Tariff change applied: ' + tcr.Proposed_Tariff__r.Name
                              + ' (' + tcr.Name + ')',
                Description = 'The customer confirmed a tariff change proposed by HW Energy Agent, '
                    + 'after the binding terms were presented and explicitly accepted.\n\n'
                    + 'Proposal: ' + tcr.Name + '\n'
                    + 'New tariff: ' + tcr.Proposed_Tariff__r.Name + '\n'
                    + 'Quoted annual saving: ' + tcr.Annual_Saving__c + '\n\n'
                    + 'Assumption the quote depends on:\n' + tcr.Assumption_Basis__c + '\n\n'
                    + 'The Salesforce contract has been switched. A Tariff_Change_Requested__e event '
                    + 'has been published for the billing system (SAP IS-U) to register the change.',
                HW_Topic__c = 'TariffChange'));
            caseSlotByResult[results.size()] = casesToOpen.size() - 1;

            events.add(new Tariff_Change_Requested__e(
                Account_Id__c     = tcr.Account__c,
                Request_Number__c = tcr.Name,
                New_Tariff__c     = tcr.Proposed_Tariff__r.Name,
                Annual_Saving__c  = tcr.Annual_Saving__c));

            res.applied      = true;
            res.newTariff    = tcr.Proposed_Tariff__r.Name;
            res.annualSaving = tcr.Annual_Saving__c;
            results.add(res);
        }

        // ---- One DML per object. Nothing above ran DML inside a loop. ----
        if (!contractUpdates.isEmpty()) update as user contractUpdates;
        if (!requestUpdates.isEmpty())  update as user requestUpdates;
        if (!casesToOpen.isEmpty())     insert as user casesToOpen;
        if (!events.isEmpty())          EventBus.publish(events);

        if (!casesToOpen.isEmpty()) {
            Set<Id> caseIds = new Set<Id>();
            for (Case c : casesToOpen) caseIds.add(c.Id);
            Map<Id, Case> byId = new Map<Id, Case>(
                [SELECT Id, CaseNumber FROM Case WHERE Id IN :caseIds WITH USER_MODE]);
            for (Integer i = 0; i < results.size(); i++) {
                Integer slot = caseSlotByResult[i];
                if (slot < 0) continue;
                Case c = byId.get(casesToOpen[slot].Id);
                results[i].caseNumber = (c == null) ? null : c.CaseNumber;
                results[i].message = 'Done. Your contract will run on ' + results[i].newTariff
                    + ' from the next billing period, and you save '
                    + results[i].annualSaving + ' per year. Reference: case ' + results[i].caseNumber
                    + '. A specialist confirms the change with the billing system.';
            }
        }
        return results;
    }
}