/**
 * HWMoveService — registers a customer's move (Umzug), the most common non-billing request a
 * German energy retailer handles.
 *
 * The interesting part is not the Case it opens. It is what it REFUSES to open one without.
 *
 * A move is a billing event: HanseWatt must close the old meter, issue a final bill, and (if the
 * customer stays) open supply at the new address. Every one of those steps needs a fact only the
 * CUSTOMER has — the move-out date, the final meter reading, the new address. An agent that
 * cheerfully files a move case with a plausible-looking date has not helped anyone; it has put a
 * fabricated number into a billing process.
 *
 * So this service treats those facts the way ADR-020/021 treat consent and identity: as things
 * the model cannot supply. Each one is validated, and a missing or impossible one produces a
 * refusal with a machine-readable reason and ZERO DML. The agent is told to go back and ask.
 *
 * Standard (ADR-006): with sharing, SOQL WITH USER_MODE, DML "as user", bulk-safe.
 */
public with sharing class HWMoveService {

    /** A move can be filed at most a year ahead — beyond that the reading would be meaningless. */
    @TestVisible private static final Integer MAX_MONTHS_AHEAD = 12;

    /** What the customer tells us. */
    public class MoveRequest {
        public Id      accountId;
        public Date    moveOutDate;
        public Decimal finalMeterReading;
        public Boolean staysCustomer;
        public String  newAddress;
    }

    public class MoveResult {
        public Boolean registered = false;
        public String  caseNumber;
        public Id      caseId;
        public String  refusalReason;   // see REFUSALS below
        public String  message;
    }

    public static List<MoveResult> registerMoves(List<MoveRequest> requests) {
        List<MoveResult> out = new List<MoveResult>();
        if (requests == null || requests.isEmpty()) {
            return out;
        }

        // ONE query: does this account actually have a supply contract to move?
        Set<Id> accountIds = new Set<Id>();
        for (MoveRequest r : requests) {
            if (r != null && r.accountId != null) accountIds.add(r.accountId);
        }
        Map<Id, Service_Contract__c> contractByAccount = new Map<Id, Service_Contract__c>();
        if (!accountIds.isEmpty()) {
            String query =
                'SELECT Id, Account__c, Meter__c ' +
                'FROM Service_Contract__c ' +
                'WHERE Account__c IN :accountIds';
            Map<String, Object> binds = new Map<String, Object>{ 'accountIds' => accountIds };
            for (Service_Contract__c sc :
                    (List<Service_Contract__c>) Database.queryWithBinds(query, binds, AccessLevel.USER_MODE)) {
                contractByAccount.put(sc.Account__c, sc);
            }
        }

        Date today    = Date.today();
        Date latest   = today.addMonths(MAX_MONTHS_AHEAD);

        // Build the cases we CAN file; remember which request each one came from.
        List<HWCaseService.NewCase> cases = new List<HWCaseService.NewCase>();
        List<Integer> caseForRequest = new List<Integer>();

        for (Integer i = 0; i < requests.size(); i++) {
            MoveRequest r = requests[i];
            MoveResult res = new MoveResult();
            out.add(res);

            if (r == null || r.accountId == null) {
                refuse(res, 'NO_IDENTITY',
                    'The customer is not verified. Verify them with their email AND customer number '
                    + 'first. Do not file a move without a verified account.');
                continue;
            }
            if (!contractByAccount.containsKey(r.accountId)) {
                refuse(res, 'NO_CONTRACT',
                    'This customer has no active supply contract, so there is nothing to move. '
                    + 'Offer to open a case so a specialist can look at the account.');
                continue;
            }
            if (r.moveOutDate == null) {
                refuse(res, 'MISSING_MOVE_DATE',
                    'Ask the customer for the exact date they move out (Auszugsdatum). Do NOT guess '
                    + 'it, do not infer it from words like "next month", and do not file the move '
                    + 'until they give you a real date.');
                continue;
            }
            if (r.moveOutDate < today) {
                refuse(res, 'MOVE_DATE_IN_THE_PAST',
                    'The move-out date given is in the past. Ask the customer to confirm the correct '
                    + 'date. Do not file it.');
                continue;
            }
            if (r.moveOutDate > latest) {
                refuse(res, 'MOVE_DATE_TOO_FAR',
                    'A move can only be registered up to ' + MAX_MONTHS_AHEAD + ' months ahead. Ask '
                    + 'the customer to contact us closer to the date.');
                continue;
            }
            if (r.finalMeterReading == null) {
                refuse(res, 'MISSING_METER_READING',
                    'Ask the customer to read the final meter value (Zählerstand) from their meter on '
                    + 'the move-out date. NEVER estimate or invent it — an estimated reading produces '
                    + 'an estimated final bill, which is exactly what the customer wants to avoid.');
                continue;
            }
            if (r.finalMeterReading < 0) {
                refuse(res, 'IMPLAUSIBLE_METER_READING',
                    'A meter reading cannot be negative. Ask the customer to read it again.');
                continue;
            }
            if (r.staysCustomer == true && String.isBlank(r.newAddress)) {
                refuse(res, 'MISSING_NEW_ADDRESS',
                    'The customer wants to stay with HanseWatt, so we need the new address and the '
                    + 'move-in date to start supply there. Ask for it before filing the move.');
                continue;
            }

            HWCaseService.NewCase nc = new HWCaseService.NewCase();
            nc.accountId   = r.accountId;
            nc.topic       = 'Move';
            nc.subject     = 'Umzug — move-out on ' + String.valueOf(r.moveOutDate);
            nc.description =
                  'MOVE (Umzug) registered by the HanseWatt agent.\n'
                + 'Move-out date: '        + String.valueOf(r.moveOutDate) + '\n'
                + 'Final meter reading: '  + String.valueOf(r.finalMeterReading) + ' kWh '
                + '(given by the customer — not estimated)\n'
                + 'Stays a HanseWatt customer: ' + (r.staysCustomer == true ? 'YES' : 'NO') + '\n'
                + (r.staysCustomer == true
                    ? 'New supply address: ' + r.newAddress + '\n'
                    : 'Supply ends at the move-out date; a final bill is due.\n')
                + 'Next: close the old meter, issue the final bill'
                + (r.staysCustomer == true ? ', and open supply at the new address.' : '.');

            cases.add(nc);
            caseForRequest.add(i);
        }

        if (cases.isEmpty()) {
            return out;
        }

        List<HWCaseService.Created> created = HWCaseService.createCases(cases);

        for (Integer j = 0; j < created.size(); j++) {
            MoveResult res = out[caseForRequest[j]];
            res.registered = true;
            res.caseId     = created[j].caseId;
            res.caseNumber = created[j].caseNumber;
            res.message =
                  'The move is registered under case ' + created[j].caseNumber + '. Tell the customer: '
                + 'we will close the meter on the move-out date, issue a final bill from the reading '
                + 'THEY gave us (so it is not estimated), and a specialist will confirm. '
                + 'Give them the case number.';
        }
        return out;
    }

    private static void refuse(MoveResult res, String reason, String message) {
        res.registered    = false;
        res.refusalReason = reason;
        res.message       = message;
    }
}