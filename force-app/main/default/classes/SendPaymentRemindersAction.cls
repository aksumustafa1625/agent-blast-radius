/**
 * Agentforce-callable action to send Stripe payment link reminders for one or many invoices.
 * Publishes Invoice_Payment_Requested__e Platform Event so MuleSoft picks up and creates Stripe Checkout URL,
 * which then triggers the Send_Stripe_Payment_Email record-triggered flow.
 *
 * Designed to be invoked by Salesforce AI Agentforce / Einstein Copilot.
 * Input: an Invoice DocumentNumber (e.g. "DOC-000000012") OR the literal "all" to send to every unpaid invoice.
 */
public with sharing class SendPaymentRemindersAction {

    // ---- Test seams ----
    // Salesforce Industries Billing rejects `insert new Invoice(...)` in Apex tests
    // ("Can't create Invoice in Apex. Use REST API instead."). These @TestVisible seams
    // let unit tests inject in-memory Invoice records (built via JSON.deserialize) and
    // suppress the final DML update, which would fail on synthetic Ids.
    @TestVisible private static List<Invoice> testInvoicesOverride = null;
    @TestVisible private static Boolean testSkipDml = false;

    public class Request {
        @InvocableVariable(
            label='Invoice Number'
            description='Invoice DocumentNumber such as DOC-000000012, or "all" to send reminders for all unpaid invoices.'
            required=true
        )
        public String documentNumber;
    }

    public class Response {
        @InvocableVariable(label='Result Message' description='Human-readable summary of the action')
        public String outcomeMessage;

        @InvocableVariable(label='Reminders Sent' description='Number of invoices for which a reminder was sent')
        public Integer remindersSent;

        @InvocableVariable(label='Processed Invoices' description='List of invoice DocumentNumbers that were processed')
        public List<String> processedInvoices;

        @InvocableVariable(label='Total Amount' description='Sum of TotalAmountWithTax across all processed invoices')
        public Decimal totalAmount;
    }

    @InvocableMethod(
        label='Send Stripe Payment Reminders'
        description='Sends Stripe payment link emails for the specified invoice (by DocumentNumber) or for every unpaid invoice when called with "all".'
        category='TechnoStore'
    )
    public static List<Response> sendReminders(List<Request> requests) {
        List<Response> responses = new List<Response>();

        for (Request req : requests) {
            Response resp = new Response();
            resp.processedInvoices = new List<String>();
            resp.remindersSent = 0;
            resp.totalAmount = 0;

            if (req.documentNumber == null || String.isBlank(req.documentNumber)) {
                resp.outcomeMessage = 'Please provide an Invoice DocumentNumber or "all".';
                responses.add(resp);
                continue;
            }

            List<Invoice> invoices = findInvoices(req.documentNumber);

            if (invoices.isEmpty()) {
                resp.outcomeMessage = 'No matching unpaid invoices found for "' + req.documentNumber + '".';
                responses.add(resp);
                continue;
            }

            List<Invoice_Payment_Requested__e> events = new List<Invoice_Payment_Requested__e>();
            List<Invoice> invoicesToUpdate = new List<Invoice>();

            for (Invoice inv : invoices) {
                String email = (inv.BillToContact != null) ? inv.BillToContact.Email : null;
                if (email == null) {
                    continue;
                }

                Invoice_Payment_Requested__e e = new Invoice_Payment_Requested__e();
                e.Invoice_Id__c = inv.Id;
                e.Invoice_Number__c = inv.DocumentNumber;
                e.Amount__c = inv.TotalAmountWithTax;
                e.Currency_Code__c = 'USD';
                e.Customer_Email__c = email;
                e.Customer_Name__c = (inv.BillingAccount != null) ? inv.BillingAccount.Name : 'Customer';
                events.add(e);

                inv.Stripe_Payment_Status__c = 'Sent';
                invoicesToUpdate.add(inv);

                resp.processedInvoices.add(inv.DocumentNumber);
                if (inv.TotalAmountWithTax != null) {
                    resp.totalAmount += inv.TotalAmountWithTax;
                }
            }

            if (events.isEmpty()) {
                resp.outcomeMessage = 'Found ' + invoices.size() + ' invoice(s), but none have a Bill To Contact email set. No reminders sent.';
                responses.add(resp);
                continue;
            }

            EventBus.publish(events);
            if (!testSkipDml) {
                update invoicesToUpdate;
            }

            resp.remindersSent = invoicesToUpdate.size();
            resp.outcomeMessage = 'Successfully sent ' + resp.remindersSent + ' Stripe payment reminder(s) totaling $'
                + resp.totalAmount.setScale(2) + '. MuleSoft is now generating Stripe checkout URLs and emailing the customers.';
            responses.add(resp);
        }

        return responses;
    }

    private static List<Invoice> findInvoices(String identifier) {
        if (testInvoicesOverride != null) {
            return testInvoicesOverride;
        }
        if (identifier.equalsIgnoreCase('all')) {
            return [
                SELECT Id, DocumentNumber, TotalAmountWithTax, Stripe_Payment_Status__c,
                       BillToContactId, BillToContact.Email,
                       BillingAccountId, BillingAccount.Name
                FROM Invoice
                WHERE (Stripe_Payment_Status__c = 'Not Started'
                       OR Stripe_Payment_Status__c = 'Failed'
                       OR Stripe_Payment_Status__c = null)
                  AND BillToContact.Email != null
                LIMIT 50
            ];
        }
        return [
            SELECT Id, DocumentNumber, TotalAmountWithTax, Stripe_Payment_Status__c,
                   BillToContactId, BillToContact.Email,
                   BillingAccountId, BillingAccount.Name
            FROM Invoice
            WHERE DocumentNumber = :identifier
            LIMIT 1
        ];
    }
}