/**
 * HWCustomerService — resolves a HanseWatt customer Account from the credentials the customer
 * presents in conversation. Everything the agent later grounds on (bill, consumption, tariff,
 * case) hangs off the Account Id this class hands back, so this is the front door — and the
 * front door needs a lock.
 *
 * TWO-FACTOR BY DESIGN (ADR-021). An email alone is NOT enough. The customer must also present
 * the Kundennummer printed on their bill (Account.Customer_Number__c). This is exactly how a
 * German utility hotline authenticates, and it is what makes the agent's privacy refusal
 * *structural* rather than a promise in a prompt: to see Johann Huber's bill you need Johann
 * Huber's customer number. The customer asking doesn't have it. The model cannot invent it —
 * it is compared, server-side, against a stored value it never sees.
 *
 * A failed verification reveals NOTHING — not even whether the email exists. Saying "that
 * email is not registered" would turn the agent into an account-enumeration oracle.
 *
 * HanseWatt uses business Accounts with a related Contact (Person Accounts are not enabled),
 * so the email lives on Contact and we return its AccountId.
 *
 * Standard (ADR-006): with sharing, SOQL USER_MODE via Database.queryWithBinds (an inline
 * bind throws "Variable does not exist: tmpVar1" in the Agentforce action runtime), bulk-safe.
 */
public with sharing class HWCustomerService {

    /** What the customer presents. Both parts are required. */
    public class Credential {
        public String email;
        public String customerNumber;
        public Credential(String email, String customerNumber) {
            this.email = email;
            this.customerNumber = customerNumber;
        }
    }

    /** The outcome of a verification attempt. On failure it carries no customer data at all. */
    public class Verification {
        public Boolean verified = false;
        public Id     accountId;
        public String accountName;
        public String refusalReason;   // MISSING_EMAIL | MISSING_CUSTOMER_NUMBER | VERIFICATION_FAILED
    }

    /** The resolved customer (internal — never reachable from an agent action on its own). */
    public class Customer {
        public Id     accountId;
        public String accountName;
        public String customerNumber;
    }

    /**
     * Bulk-safe two-factor verification. ONE query for the whole batch.
     *
     * @param creds the credentials presented, in order
     * @return one Verification per input, in the same order
     */
    public static List<Verification> verify(List<Credential> creds) {
        List<Verification> out = new List<Verification>();
        if (creds == null || creds.isEmpty()) {
            return out;
        }

        Set<String> emails = new Set<String>();
        for (Credential c : creds) {
            if (c != null && String.isNotBlank(c.email)) emails.add(c.email.trim().toLowerCase());
        }

        Map<String, Customer> byEmail = emails.isEmpty()
            ? new Map<String, Customer>()
            : lookup(emails);

        for (Credential c : creds) {
            Verification v = new Verification();

            if (c == null || String.isBlank(c.email)) {
                v.refusalReason = 'MISSING_EMAIL';
                out.add(v);
                continue;
            }
            if (String.isBlank(c.customerNumber)) {
                v.refusalReason = 'MISSING_CUSTOMER_NUMBER';
                out.add(v);
                continue;
            }

            Customer cust = byEmail.get(c.email.trim().toLowerCase());

            // The email may be unknown, or known but paired with the wrong number. BOTH end
            // here, with the SAME reason and no data — the caller cannot tell them apart, so a
            // failed attempt confirms nothing about who is or isn't a HanseWatt customer.
            if (cust == null
                || String.isBlank(cust.customerNumber)
                || !cust.customerNumber.trim().equalsIgnoreCase(c.customerNumber.trim())) {
                v.refusalReason = 'VERIFICATION_FAILED';
                out.add(v);
                continue;
            }

            v.verified    = true;
            v.accountId   = cust.accountId;
            v.accountName = cust.accountName;
            out.add(v);
        }
        return out;
    }

    /** ONE query for the whole batch. Not public: an email alone must never resolve a customer. */
    private static Map<String, Customer> lookup(Set<String> emails) {
        Map<String, Customer> out = new Map<String, Customer>();
        String query =
            'SELECT Email, AccountId, Account.Name, Account.Customer_Number__c ' +
            'FROM Contact ' +
            'WHERE Email IN :emails AND AccountId != null';
        Map<String, Object> binds = new Map<String, Object>{ 'emails' => emails };
        for (Contact c : (List<Contact>) Database.queryWithBinds(query, binds, AccessLevel.USER_MODE)) {
            Customer cust = new Customer();
            cust.accountId      = c.AccountId;
            cust.accountName    = c.Account != null ? c.Account.Name : null;
            cust.customerNumber = c.Account != null ? c.Account.Customer_Number__c : null;
            out.put(c.Email.toLowerCase(), cust);
        }
        return out;
    }
}