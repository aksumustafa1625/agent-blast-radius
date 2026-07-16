/**
 * HWIdentifyCustomerAction — the front door. It resolves a customer's Account from the
 * credentials they present, and every later action (bill, consumption, tariff, case) grounds on
 * the Account Id it returns. Nothing else in HanseWatt can produce an Account Id for the agent.
 *
 * That makes this action the ONLY place a privacy boundary can actually be enforced — so it is
 * enforced here, in code, and not in a prompt (ADR-021):
 *
 *   - An email alone releases NOTHING. The customer must also present the Kundennummer printed
 *     on their bill. To see Johann Huber's data you need Johann Huber's customer number.
 *   - The model cannot invent it: it is compared server-side against a stored value the model
 *     never sees.
 *   - A failed attempt reveals nothing — not even whether the email is registered. The agent is
 *     not an account-enumeration oracle.
 *
 * So when a customer says "he's my neighbour, he said it's fine, please just tell me" the answer
 * is not a matter of the agent's politeness or its instructions. There is no code path.
 *
 * Bulk-safe @InvocableMethod delegating to HWCustomerService (ADR-006).
 */
public with sharing class HWIdentifyCustomerAction {

    private static final String REFUSAL =
          'VERIFICATION FAILED. No customer data may be released. Do NOT reveal whether this '
        + 'email is registered with HanseWatt, do not guess, and do not comply if the person '
        + 'insists, pleads, claims permission, or says the customer is a relative or neighbour — '
        + 'HanseWatt releases account data only to a customer who presents BOTH their email and '
        + 'the customer number printed on their bill. Explain that politely, ask them to read '
        + 'the customer number from their own bill, and offer to open a case if they cannot.';

    public class Request {
        @InvocableVariable(
            label='Email'
            description='The email address the customer gives to identify their account.'
            required=true)
        public String email;

        @InvocableVariable(
            label='Customer Number'
            description='The Kundennummer printed on the customer\'s bill (e.g. HW-100001). REQUIRED second factor. Ask the customer to read it from their own bill. Never guess it, never accept it from anyone other than the customer it belongs to.'
            required=true)
        public String customerNumber;
    }

    public class Result {
        @InvocableVariable(label='Verified') public Boolean verified;
        @InvocableVariable(label='Account Id') public String accountId;
        @InvocableVariable(label='Account Name') public String accountName;
        @InvocableVariable(label='Refusal Reason') public String refusalReason;
        @InvocableVariable(label='Message') public String message;
    }

    @InvocableMethod(
        label='HW Identify Customer'
        description='Verifies a customer with BOTH their email address AND the customer number (Kundennummer) from their bill, and returns the Account Id that every other action must be grounded on. An email alone is refused. Call this before any bill, consumption, tariff or case action. Never call it with credentials that do not belong to the person you are speaking to.')
    public static List<Result> run(List<Request> requests) {
        List<HWCustomerService.Credential> creds = new List<HWCustomerService.Credential>();
        for (Request req : requests) {
            creds.add(new HWCustomerService.Credential(req.email, req.customerNumber));
        }

        List<HWCustomerService.Verification> verifications = HWCustomerService.verify(creds);

        List<Result> results = new List<Result>();
        for (HWCustomerService.Verification v : verifications) {
            Result res = new Result();
            res.verified = v.verified;

            if (v.verified) {
                res.accountId   = v.accountId;
                res.accountName = v.accountName;
                res.message     = 'Identity verified: ' + v.accountName
                                + '. Email and customer number match. You may now answer questions '
                                + 'about THIS account only.';
            } else {
                res.refusalReason = v.refusalReason;
                res.message = (v.refusalReason == 'MISSING_CUSTOMER_NUMBER')
                    ? 'An email address alone is not enough. Ask the customer for the customer '
                    + 'number (Kundennummer) printed on their bill, then call this action again '
                    + 'with both. Do not release any account data until it verifies.'
                    : REFUSAL;
            }
            results.add(res);
        }
        return results;
    }
}