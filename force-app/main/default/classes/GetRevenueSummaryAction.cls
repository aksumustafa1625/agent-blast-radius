/**
 * Agentforce-callable action that returns a revenue summary across native Invoice records.
 * Aggregates Stripe_Payment_Status__c=Paid invoices over a time window (default 90 days).
 *
 * Designed to be invoked by Salesforce AI Agentforce / Einstein Copilot.
 */
public with sharing class GetRevenueSummaryAction {

    public class Request {
        @InvocableVariable(
            label='Days Back'
            description='How many days back to look for paid invoices (e.g. 30, 90, 180, 365). Defaults to 90.'
            required=false
        )
        public Integer daysBack;
    }

    public class Response {
        @InvocableVariable(label='Result Message' description='Human-readable revenue summary')
        public String outcomeMessage;

        @InvocableVariable(label='Total Revenue Collected')
        public Decimal totalRevenue;

        @InvocableVariable(label='Number of Paid Invoices')
        public Integer paidCount;

        @InvocableVariable(label='Number of Outstanding Invoices')
        public Integer unpaidCount;

        @InvocableVariable(label='Outstanding Amount')
        public Decimal outstandingAmount;

        @InvocableVariable(label='Days Window')
        public Integer windowDays;
    }

    @InvocableMethod(
        label='Get Revenue Summary'
        description='Returns total Stripe-collected revenue, paid count, and outstanding receivables for a time window in days.'
        category='TechnoStore'
    )
    public static List<Response> getSummary(List<Request> requests) {
        List<Response> responses = new List<Response>();

        for (Request req : requests) {
            Response resp = new Response();
            Integer days = (req.daysBack != null && req.daysBack > 0) ? req.daysBack : 90;
            resp.windowDays = days;

            DateTime windowStart = DateTime.now().addDays(-days);

            AggregateResult[] paidAgg = [
                SELECT COUNT(Id) cnt, SUM(TotalAmountWithTax) total
                FROM Invoice
                WHERE Stripe_Payment_Status__c = 'Paid'
                  AND Paid_Date__c >= :windowStart
            ];
            AggregateResult[] unpaidAgg = [
                SELECT COUNT(Id) cnt, SUM(TotalAmountWithTax) total
                FROM Invoice
                WHERE (Stripe_Payment_Status__c = 'Sent'
                       OR Stripe_Payment_Status__c = 'Not Started'
                       OR Stripe_Payment_Status__c = 'Failed'
                       OR Stripe_Payment_Status__c = null)
                  AND Status = 'Posted'
            ];

            resp.paidCount = (Integer) paidAgg[0].get('cnt');
            resp.totalRevenue = (Decimal) paidAgg[0].get('total');
            if (resp.totalRevenue == null) resp.totalRevenue = 0;

            resp.unpaidCount = (Integer) unpaidAgg[0].get('cnt');
            resp.outstandingAmount = (Decimal) unpaidAgg[0].get('total');
            if (resp.outstandingAmount == null) resp.outstandingAmount = 0;

            resp.outcomeMessage = 'Last ' + days + ' days: collected $' + resp.totalRevenue.setScale(2)
                + ' across ' + resp.paidCount + ' paid invoice(s). Outstanding: $'
                + resp.outstandingAmount.setScale(2) + ' across ' + resp.unpaidCount + ' invoice(s).';
            responses.add(resp);
        }

        return responses;
    }
}