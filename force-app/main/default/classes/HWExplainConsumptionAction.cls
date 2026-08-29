/**
 * HWExplainConsumptionAction — the Agentforce-callable bridge that returns a customer's
 * consumption anomaly (latest vs trailing average) and a grounded explanation. The agent
 * calls this for the "why is my bill so high?" topic; it never invents the figure.
 *
 * Bulk-safe @InvocableMethod delegating to HWConsumptionService (ADR-006).
 */
public with sharing class HWExplainConsumptionAction {

    public class Request {
        // String, not Id — the value comes from the LLM and may be anything. HWIds maps a bad
        // value to null, which lands in the refusal below instead of an Apex coercion exception.
        @InvocableVariable(label='Account Id' description='The VERIFIED customer Account Id, from HW Verify Customer. Never put an email address or a guessed value here.')
        public String accountId;
    }

    public class Result {
        @InvocableVariable(label='Latest kWh') public Decimal latestKwh;
        @InvocableVariable(label='Average kWh') public Decimal averageKwh;
        @InvocableVariable(label='Anomaly Percent') public Decimal anomalyPercent;
        @InvocableVariable(label='Explanation') public String explanation;
        @InvocableVariable(label='Citation') public String citation;
    }

    @InvocableMethod(
        label='HW Explain Consumption Anomaly'
        description='Returns the latest usage vs trailing average for a customer and a grounded, citable explanation.')
    public static List<Result> run(List<Request> requests) {
        List<Id> parsed = new List<Id>();
        Set<Id> accountIds = new Set<Id>();
        for (Request req : requests) {
            Id acc = HWIds.accountId(req.accountId);
            parsed.add(acc);
            if (acc != null) accountIds.add(acc);
        }
        Map<Id, HWConsumptionService.Anomaly> byAccount =
            HWConsumptionService.anomaliesByAccount(accountIds);

        List<Result> results = new List<Result>();
        for (Integer i = 0; i < requests.size(); i++) {
            Result res = new Result();
            if (parsed[i] == null) {
                // No verified account — drive the agent to verify the customer first instead of
                // guessing. Honest grounding: no account, no figure. And no other customer's.
                res.explanation = 'No verified customer. I cannot look up usage without one, and '
                    + 'I must not look up anyone else\'s. Verify the customer with their email '
                    + 'AND their customer number first.';
                res.citation = '';
                results.add(res);
                continue;
            }
            HWConsumptionService.Anomaly a = byAccount.get(parsed[i]);
            if (a != null && a.latestKwh != null) {
                res.latestKwh = a.latestKwh;
                res.averageKwh = a.averageKwh;
                res.anomalyPercent = a.anomalyPercent;
                res.explanation = a.explanation;
                res.citation = 'Data 360 — Meter Reading (unified consumption)';
            } else {
                res.explanation = 'No consumption data found for this customer.';
                res.citation = '';
            }
            results.add(res);
        }
        return results;
    }
}