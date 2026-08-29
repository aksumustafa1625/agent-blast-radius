/**
 * HWRegisterMoveAction — closes the Umzug loop.
 *
 * Before this action the agent could only *explain* a move (from the cited Knowledge article) and
 * then had nothing to do with the customer's answer. The customer said "I move on 1 September, my
 * final reading is 41 250, and I'd like to stay a HanseWatt customer" — and nothing happened. A
 * demo that ends there is a chatbot; a service agent has to *file* it.
 *
 * The action files a Move case (`HW_Topic__c = 'Move'`, the record type that has existed since
 * Faz 1 and had no caller until now) — but only once the customer has supplied the facts that
 * only they can supply. A missing move-out date or meter reading is a REFUSAL, not something to
 * estimate: an invented reading becomes an invented final bill.
 *
 * Bulk-safe @InvocableMethod delegating to HWMoveService (ADR-006).
 */
public with sharing class HWRegisterMoveAction {

    public class Request {
        @InvocableVariable(
            label='Account Id'
            description='The VERIFIED customer\'s Account Id, from HW Verify Customer. Required.'
            required=true)
        public String accountId;

        @InvocableVariable(
            label='Move Out Date'
            description='The exact date the customer moves out (Auszugsdatum). Ask them for it. Never guess it and never derive it from a vague phrase like "next month".'
            required=true)
        public Date moveOutDate;

        @InvocableVariable(
            label='Final Meter Reading'
            description='The final meter value (Zählerstand) in kWh, read by the customer from their own meter. NEVER estimate or invent this — an estimated reading produces an estimated final bill.'
            required=true)
        public Decimal finalMeterReading;

        @InvocableVariable(
            label='Stays Customer'
            description='True if the customer wants to keep HanseWatt at their new address, false if the supply should simply end.')
        public Boolean staysCustomer;

        @InvocableVariable(
            label='New Address'
            description='The new supply address. Required when the customer stays with HanseWatt.')
        public String newAddress;
    }

    public class Result {
        @InvocableVariable(label='Registered') public Boolean registered;
        @InvocableVariable(label='Case Number') public String caseNumber;
        @InvocableVariable(label='Refusal Reason') public String refusalReason;
        @InvocableVariable(label='Message') public String message;
    }

    @InvocableMethod(
        label='HW Register Move'
        description='Files a customer\'s move (Umzug) as a Move case once they have given the move-out date and the final meter reading. Call it only for a VERIFIED customer. If a required fact is missing it refuses and tells you what to ask for — never make one up.')
    public static List<Result> run(List<Request> requests) {
        List<HWMoveService.MoveRequest> moves = new List<HWMoveService.MoveRequest>();
        for (Request req : requests) {
            HWMoveService.MoveRequest m = new HWMoveService.MoveRequest();
            m.accountId = HWIds.accountId(req.accountId);   // a bad id is a refusal, not a crash
            m.moveOutDate       = req.moveOutDate;
            m.finalMeterReading = req.finalMeterReading;
            m.staysCustomer     = req.staysCustomer;
            m.newAddress        = req.newAddress;
            moves.add(m);
        }

        List<Result> results = new List<Result>();
        for (HWMoveService.MoveResult mr : HWMoveService.registerMoves(moves)) {
            Result res = new Result();
            res.registered    = mr.registered;
            res.caseNumber    = mr.caseNumber;
            res.refusalReason = mr.refusalReason;
            res.message       = mr.message;
            results.add(res);
        }
        return results;
    }
}