/**
 * HWGetLatestBillAction — the Agentforce-callable action that returns a customer's most recent
 * energy bill so the agent can answer "how much is my latest bill?" with the real amount,
 * period, usage and status. Pair it with HW Identify Customer to get the Account Id first.
 *
 * Bulk-safe @InvocableMethod delegating to HWBillingService (ADR-006).
 */
public with sharing class HWGetLatestBillAction {

    public class Request {
        // String, not Id, on purpose: the value comes from the LLM and may be anything at all
        // (an email address, "unknown", a hallucinated id). HWIds turns that into null, which
        // lands in the "not identified" refusal below — instead of an Apex coercion exception
        // thrown before our code even runs. See HWIds.
        @InvocableVariable(label='Account Id' description='The VERIFIED customer Account Id, from HW Verify Customer. Never put an email address or a guessed value here — if the customer is not verified, verify them first.')
        public String accountId;
    }

    public class Result {
        @InvocableVariable(label='Bill Number') public String billNumber;
        @InvocableVariable(label='Period Start') public String periodStart;
        @InvocableVariable(label='Period End') public String periodEnd;
        @InvocableVariable(label='Amount') public Decimal amount;
        @InvocableVariable(label='Currency') public String currencyCode;
        @InvocableVariable(label='Consumption kWh') public Decimal consumptionKwh;
        @InvocableVariable(label='Status') public String status;
        @InvocableVariable(label='Summary') public String summary;
        @InvocableVariable(label='Citation') public String citation;
    }

    @InvocableMethod(
        label='HW Get Latest Bill'
        description='Returns the most recent energy bill for a customer (amount, period, usage, status) from the billing record.')
    public static List<Result> run(List<Request> requests) {
        List<Id> parsed = new List<Id>();
        Set<Id> accountIds = new Set<Id>();
        for (Request req : requests) {
            Id acc = HWIds.accountId(req.accountId);
            parsed.add(acc);
            if (acc != null) accountIds.add(acc);
        }
        Map<Id, HWBillingService.Bill> byAccount = HWBillingService.latestByAccount(accountIds);

        List<Result> results = new List<Result>();
        for (Integer i = 0; i < requests.size(); i++) {
            Result res = new Result();
            if (parsed[i] == null) {
                res.summary = 'No verified customer. I cannot look up a bill without one, and I '
                    + 'must not look up a bill for anyone else. Verify the customer with their '
                    + 'email AND their customer number first.';
                res.citation = '';
                results.add(res);
                continue;
            }
            HWBillingService.Bill b = byAccount.get(parsed[i]);
            if (b != null) {
                res.billNumber     = b.billNumber;
                res.periodStart    = b.periodStart != null ? String.valueOf(b.periodStart) : null;
                res.periodEnd      = b.periodEnd != null ? String.valueOf(b.periodEnd) : null;
                res.amount         = b.amount;
                res.currencyCode   = b.currencyCode;
                res.consumptionKwh = b.consumptionKwh;
                res.status         = b.status;
                res.summary        = 'Latest bill ' + b.billNumber + ' covers ' + b.periodStart
                    + ' to ' + b.periodEnd + ': ' + b.amount + ' ' + b.currencyCode + ' for '
                    + b.consumptionKwh + ' kWh. Status: ' + b.status + '.';
                res.citation       = 'HanseWatt billing (Energy Bill record)';
            } else {
                res.summary  = 'No bill was found for this customer yet.';
                res.citation = '';
            }
            results.add(res);
        }
        return results;
    }
}