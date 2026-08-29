/**
 * HWProposeTariffChangeAction — step 1 of the consent handshake (ADR-020).
 *
 * The agent costs every comparable tariff at the customer's OWN consumption and, if a
 * cheaper one exists, mints a **server-issued, expiring proposal** (`Tariff_Change_Request__c`).
 * The proposal's request number is returned to the agent — and that number is the ONLY
 * way the change can later be applied (see HWConfirmTariffChangeAction).
 *
 * Why this matters (the thing a Principal Engineer will poke at):
 *   A `customerConfirmed = true` Boolean is NOT a structural guardrail — the model fills
 *   it in, so a jailbroken or hallucinating model can simply set it. Here, consent is a
 *   **persisted state machine with an expiry**: the request number exists only in the
 *   output of THIS step, so the confirm step cannot be reached by a model that skipped it.
 *   The handshake is enforced by the data flow, not by hoping the prompt held.
 *
 * This action performs a benign write (it creates a proposal); it never touches the
 * customer's contract.
 *
 * Bulk-safe @InvocableMethod delegating to HWTariffService (ADR-006).
 */
public with sharing class HWProposeTariffChangeAction {

    /** How long a quoted proposal stays valid. Consent is perishable. */
    private static final Integer VALID_MINUTES = 30;

    public class Request {
        @InvocableVariable(
            label='Account Id'
            description='The VERIFIED customer Account Id, from HW Verify Customer. Never pass an email address, a guessed value, or an account the customer has not been verified as.'
            required=true)
        public String accountId;   // String, not Id: the LLM fills it — see HWIds
    }

    /** The only way an Account Id enters this action. A bad value becomes null, not an exception. */
    private static Id acc(Request req) {
        return HWIds.accountId(req.accountId);
    }

    public class Result {
        @InvocableVariable(label='Found') public Boolean found;
        @InvocableVariable(label='Current Tariff') public String currentTariff;
        @InvocableVariable(label='Recommended Tariff') public String recommendedTariff;
        @InvocableVariable(label='Annual Saving') public Decimal annualSaving;
        @InvocableVariable(label='Currency') public String currencyCode;
        @InvocableVariable(label='Is Conditional') public Boolean isConditional;
        @InvocableVariable(label='Assumption Basis') public String assumptionBasis;
        @InvocableVariable(label='Comparison') public String comparison;
        @InvocableVariable(label='Request Number') public String requestNumber;
        @InvocableVariable(label='Citation') public String citation;
        @InvocableVariable(label='Message') public String message;
    }

    @InvocableMethod(
        label='HW Propose Tariff Change'
        description='Costs every comparable tariff at the customer\'s own consumption (price per kWh AND monthly base fee) and, if a cheaper one exists, creates an expiring proposal and returns its request number. Use for "my bill is too high", "switch me to a cheaper tariff", "which tariff suits me". Does NOT change the contract.')
    public static List<Result> run(List<Request> requests) {
        Set<Id> accountIds = new Set<Id>();
        for (Request req : requests) {
            if (acc(req) != null) accountIds.add(acc(req));
        }
        Map<Id, HWTariffService.Recommendation> byAccount =
            HWTariffService.recommendByAccount(accountIds);

        // Collect the proposals to mint — one DML for all of them (bulk-safe).
        List<Tariff_Change_Request__c> toInsert = new List<Tariff_Change_Request__c>();
        List<Request> minted = new List<Request>();
        Map<Id, Id> contractByAccount = contractIds(accountIds);

        for (Request req : requests) {
            HWTariffService.Recommendation r =
                (acc(req) != null) ? byAccount.get(acc(req)) : null;
            if (r == null || r.found != true) continue;
            // Only mint a proposal when there is actually something to switch TO.
            if (r.bestAtCurrentId == null || r.bestAtCurrentId == r.currentTariffId) continue;

            Tariff_Change_Request__c tcr = new Tariff_Change_Request__c();
            tcr.Account__c              = acc(req);
            tcr.Proposed_Tariff__c      = r.bestAtCurrentId;
            tcr.Service_Contract_Ref__c = contractByAccount.get(acc(req));
            tcr.Annual_Saving__c        = r.savingAtCurrent;
            tcr.Assumption_Basis__c     = r.assumptionBasis;
            tcr.Status__c               = 'Proposed';
            tcr.Expires_At__c           = System.now().addMinutes(VALID_MINUTES);
            toInsert.add(tcr);
            minted.add(req);
        }
        if (!toInsert.isEmpty()) {
            insert as user toInsert;
        }

        // Re-read the auto-numbers: the request number is minted by the platform, not by us
        // (and certainly not by the model).
        Map<Id, String> numberById = new Map<Id, String>();
        if (!toInsert.isEmpty()) {
            Set<Id> ids = new Set<Id>();
            for (Tariff_Change_Request__c t : toInsert) ids.add(t.Id);
            for (Tariff_Change_Request__c t :
                    [SELECT Id, Name FROM Tariff_Change_Request__c WHERE Id IN :ids WITH USER_MODE]) {
                numberById.put(t.Id, t.Name);
            }
        }
        Map<Id, String> numberByAccount = new Map<Id, String>();
        for (Integer i = 0; i < toInsert.size(); i++) {
            numberByAccount.put(acc(minted[i]), numberById.get(toInsert[i].Id));
        }

        List<Result> results = new List<Result>();
        for (Request req : requests) {
            Result res = new Result();
            if (acc(req) == null) {
                res.found = false;
                res.message = 'No verified customer. I cannot compare tariffs without one, and I '
                    + 'must not do it for anyone else. Verify the customer with their email AND '
                    + 'their customer number first.';
                results.add(res);
                continue;
            }
            HWTariffService.Recommendation r = byAccount.get(acc(req));
            if (r == null || r.found != true) {
                res.found = false;
                res.message = (r == null) ? 'No tariff comparison is available for this customer.'
                                          : r.message;
                results.add(res);
                continue;
            }

            res.found            = true;
            res.currentTariff    = r.currentTariffName;
            res.currencyCode     = r.currencyIso;
            res.isConditional    = r.isConditional;
            res.assumptionBasis  = r.assumptionBasis;
            res.comparison       = r.comparison;
            res.citation         = r.citation;
            res.recommendedTariff = r.bestAtCurrentName;
            res.annualSaving      = r.savingAtCurrent;
            res.requestNumber     = numberByAccount.get(acc(req));

            if (res.requestNumber == null) {
                // Already on the cheapest tariff — say so honestly, do not invent a switch.
                res.message = 'The customer is already on the cheapest comparable tariff at their '
                    + 'consumption. Do not propose a switch; tell them so.';
            } else if (r.isConditional == true) {
                res.message = 'IMPORTANT: this recommendation is CONDITIONAL. State the assumption '
                    + 'in Assumption Basis to the customer and ASK whether the higher consumption '
                    + 'is permanent. Quote the saving, then ask them to confirm. Only if they '
                    + 'confirm, call HW Confirm Tariff Change with request number '
                    + res.requestNumber + '.';
            } else {
                res.message = 'Quote the saving and the comparison, then ask the customer to confirm. '
                    + 'Only if they confirm, call HW Confirm Tariff Change with request number '
                    + res.requestNumber + '.';
            }
            results.add(res);
        }
        return results;
    }

    /** The customer's active contract id — needed to link the proposal. One query. */
    private static Map<Id, Id> contractIds(Set<Id> accountIds) {
        Map<Id, Id> out = new Map<Id, Id>();
        if (accountIds == null || accountIds.isEmpty()) return out;
        String q = 'SELECT Id, Account__c FROM Service_Contract__c '
                 + 'WHERE Account__c IN :accIds AND Status__c = \'Active\'';
        Map<String, Object> binds = new Map<String, Object>{ 'accIds' => accountIds };
        for (Service_Contract__c sc :
                (List<Service_Contract__c>) Database.queryWithBinds(q, binds, AccessLevel.USER_MODE)) {
            out.put(sc.Account__c, sc.Id);
        }
        return out;
    }
}