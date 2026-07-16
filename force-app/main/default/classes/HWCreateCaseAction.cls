/**
 * HWCreateCaseAction — the Agentforce-callable action that logs a support Case for a customer
 * (billing dispute, move, complaint, ...). Pair it with HW Identify Customer to get the Account
 * Id first. The new Case flows into the Faz 1 SLA + Omni-Channel routing for human follow-up.
 *
 * Bulk-safe @InvocableMethod delegating to HWCaseService (ADR-006).
 */
public with sharing class HWCreateCaseAction {

    public class Request {
        // String, not Id — the value comes from the LLM. HWIds maps a bad value to null, which
        // lands in the refusal below instead of an Apex coercion exception.
        @InvocableVariable(label='Account Id' description='The VERIFIED customer Account Id, from HW Verify Customer. Never put an email address or a guessed value here.')
        public String accountId;
        @InvocableVariable(label='Topic' description='Category: Billing, Consumption, TariffChange, Move, Outage, Complaint, or Other.')
        public String topic;
        @InvocableVariable(label='Subject' description='A short subject line for the case.')
        public String subject;
        @InvocableVariable(label='Description' description='The details of the customer request.')
        public String description;
    }

    public class Result {
        @InvocableVariable(label='Created') public Boolean created;
        @InvocableVariable(label='Case Number') public String caseNumber;
        @InvocableVariable(label='Message') public String message;
    }

    @InvocableMethod(
        label='HW Create Case'
        description='Logs a support case for the customer (billing dispute, move, complaint, etc.) and hands it to the service queue.')
    public static List<Result> run(List<Request> requests) {
        List<HWCaseService.NewCase> toCreate = new List<HWCaseService.NewCase>();
        List<Request> creatable = new List<Request>();
        List<Result> results = new List<Result>();

        for (Request req : requests) {
            Id acc = HWIds.accountId(req.accountId);
            if (acc == null) {
                Result res = new Result();
                res.created = false;
                res.message = 'No verified customer. I cannot open a case without one, and I must '
                    + 'not open one against someone else\'s account. Verify the customer with their '
                    + 'email AND their customer number first.';
                results.add(res);
                continue;
            }
            HWCaseService.NewCase nc = new HWCaseService.NewCase();
            nc.accountId = acc;
            nc.topic = req.topic;
            nc.subject = req.subject;
            nc.description = req.description;
            toCreate.add(nc);
            creatable.add(req);
        }

        List<HWCaseService.Created> made = HWCaseService.createCases(toCreate);
        for (Integer i = 0; i < made.size(); i++) {
            Result res = new Result();
            res.created = true;
            res.caseNumber = made[i].caseNumber;
            res.message = 'I have opened case ' + made[i].caseNumber
                + ' for you. A HanseWatt specialist will follow up shortly.';
            results.add(res);
        }
        return results;
    }
}