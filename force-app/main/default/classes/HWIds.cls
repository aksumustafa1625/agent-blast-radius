/**
 * HWIds — the boundary guard for every Account Id the agent hands to an action.
 *
 * Why this exists (learned the hard way, in a demo recording):
 *
 * The actions used to declare `public Id accountId`. That looks safe — it isn't. The value is
 * supplied by the LLM, and the LLM will happily put something that is not an Id there. When a
 * customer asked for ANOTHER customer's bill, the planner passed the *email address* into the
 * Account Id slot. Apex could not coerce it, threw before a single line of our code ran, and the
 * agent said "Ein Fehler ist aufgetreten" — a stack trace where a privacy refusal belonged.
 *
 * The lesson generalises: an action's input is UNTRUSTED. It is not a parameter from a colleague's
 * code, it is a string a language model chose. So every action now takes the id as `String` and
 * parses it HERE. A blank, malformed, or wrong-sObject value returns null — and null already
 * lands in each action's "the customer is not identified" refusal, which is exactly the right
 * answer. A bad id is a refusal, never an exception.
 */
public with sharing class HWIds {

    /**
     * @param raw whatever the model put in the Account Id slot
     * @return a real Account Id, or null if it was blank, unparseable, or an id of another object
     */
    public static Id accountId(String raw) {
        if (String.isBlank(raw)) {
            return null;
        }
        try {
            Id parsed = Id.valueOf(raw.trim());
            // An Opportunity id is not an Account id. Reject it rather than query on it.
            return (parsed.getSObjectType() == Account.SObjectType) ? parsed : null;
        } catch (Exception e) {
            return null;   // "j.huber@example.at", "unknown", "" — all just mean: not identified
        }
    }
}