/**
 * HWTariffService — the money leg of the grounding story (ADR-020).
 *
 *   figures    -> Data 360        (HWConsumptionService: 520 vs 316 kWh = +64.6 %)
 *   procedure  -> Knowledge       (HWKnowledgeService: cited article)
 *   MONEY      -> Tariff__c rows  (this service: arithmetic the LLM cannot invent)
 *
 * The intellectual core is the **Grundgebühr trap**: a tariff with a lower
 * Arbeitspreis (price per kWh) but a higher Grundpreis (monthly base fee) can be
 * MORE expensive for a given customer. So "switch me to a cheaper tariff" cannot be
 * answered by picking the lowest headline price — the genuinely cheapest tariff can
 * only be found by costing every tariff AT THIS CUSTOMER'S ACTUAL consumption.
 *
 * With the seeded HanseWatt tariffs the break-even is 375 kWh/month, which makes the
 * recommendation genuinely CONDITIONAL for Lena:
 *
 *   Lena, trailing average 316 kWh -> Strom Basis is cheaper (EV would cost ~28 EUR MORE)
 *   Lena, if the 520 kWh persists  -> EV-Tarif is cheaper  (~70 EUR/year saving)
 *
 * So the agent must not confidently recommend a switch: it must state the assumption
 * the answer depends on ("only if the new load is permanent"). That is the difference
 * between arithmetic and judgement — and it is why this is an agent action and not a
 * Flow.
 *
 * Standard (ADR-006): with sharing, SOQL WITH USER_MODE, bulk-safe (one query for the
 * tariff catalogue and one for the contracts, regardless of how many customers are
 * asked about), no SOQL/DML in loops.
 */
public with sharing class HWTariffService {

    /** How many months of the customer's consumption an annual cost covers. */
    private static final Integer MONTHS = 12;

    /** A tariff costed at a specific annual consumption. */
    public class TariffCost implements Comparable {
        public Id      tariffId;
        public String  tariffName;
        public String  currencyIso;
        public Decimal pricePerKwh;
        public Decimal baseFeeMonthly;
        public Decimal annualCost;

        public Integer compareTo(Object other) {
            TariffCost o = (TariffCost) other;
            if (this.annualCost == o.annualCost) return 0;
            return this.annualCost > o.annualCost ? 1 : -1;
        }
    }

    /**
     * The full, grounded recommendation for one customer — deliberately carrying BOTH
     * scenarios so the agent can be honest about what it does not know.
     */
    public class Recommendation {
        public Boolean found;                    // did we have enough data at all?
        public String  message;                  // set when found = false

        public Decimal baselineKwhMonth;         // trailing average (316)
        public Decimal currentKwhMonth;          // latest reading (520)
        public Boolean anomalyPresent;           // latest materially above baseline

        public Id      currentTariffId;
        public String  currentTariffName;
        public Decimal currentAnnualAtBaseline;
        public Decimal currentAnnualAtCurrent;

        public String  bestAtBaselineName;       // cheapest if usage returns to normal
        public Id      bestAtBaselineId;
        public Decimal bestAnnualAtBaseline;
        public Decimal savingAtBaseline;         // vs the customer's current tariff

        public String  bestAtCurrentName;        // cheapest if the new load is permanent
        public Id      bestAtCurrentId;
        public Decimal bestAnnualAtCurrent;
        public Decimal savingAtCurrent;

        public Boolean isConditional;            // the two scenarios disagree
        public String  assumptionBasis;          // the fact the answer depends on
        public String  comparison;               // the table the agent may quote
        public String  citation;
        public String  currencyIso;
    }

    /**
     * True annual cost of one tariff at a given annual consumption.
     * PURE — no SOQL, no DML. This is the unit the Grundgebühr trap is proven on,
     * and it is testable for free.
     */
    public static Decimal annualCost(Decimal pricePerKwh, Decimal baseFeeMonthly, Decimal annualKwh) {
        if (pricePerKwh == null || baseFeeMonthly == null || annualKwh == null) {
            throw new HWTariffException('annualCost requires pricePerKwh, baseFeeMonthly and annualKwh.');
        }
        if (pricePerKwh < 0 || baseFeeMonthly < 0 || annualKwh < 0) {
            throw new HWTariffException('annualCost inputs must be non-negative.');
        }
        return ((pricePerKwh * annualKwh) + (baseFeeMonthly * MONTHS)).setScale(2);
    }

    /**
     * Cost every tariff of the given type at the supplied annual consumption,
     * cheapest first. Pure once the catalogue is loaded — the caller passes the rows
     * in, so this stays bulk-safe (one catalogue query serves every customer).
     */
    @TestVisible
    private static List<TariffCost> rank(List<Tariff__c> catalogue, Decimal annualKwh) {
        List<TariffCost> costs = new List<TariffCost>();
        for (Tariff__c t : catalogue) {
            if (t.Price_per_kWh__c == null || t.Base_Fee__c == null) {
                continue; // one malformed row must not break the recommendation
            }
            TariffCost c = new TariffCost();
            c.tariffId       = t.Id;
            c.tariffName     = t.Name;
            c.currencyIso    = (String) t.get('CurrencyIsoCode');
            c.pricePerKwh    = t.Price_per_kWh__c;
            c.baseFeeMonthly = t.Base_Fee__c;
            c.annualCost     = annualCost(t.Price_per_kWh__c, t.Base_Fee__c, annualKwh);
            costs.add(c);
        }
        costs.sort();
        return costs;
    }

    /**
     * Bulk-safe: ONE query for the tariff catalogue, ONE for the contracts, and one
     * (already bulk-safe) call into HWConsumptionService — regardless of how many
     * accounts are asked about.
     *
     * @param accountIds the VERIFIED customer accounts (identity is scoped by the caller)
     * @return map of accountId -> Recommendation
     */
    public static Map<Id, Recommendation> recommendByAccount(Set<Id> accountIds) {
        Map<Id, Recommendation> out = new Map<Id, Recommendation>();
        if (accountIds == null || accountIds.isEmpty()) {
            return out;
        }

        // 1) The customer's live contract + the tariff they are on today.
        Map<Id, Service_Contract__c> contractByAccount = new Map<Id, Service_Contract__c>();
        String contractQuery =
            'SELECT Id, Account__c, Status__c, Tariff__c, Tariff__r.Name, Tariff__r.Type__c, ' +
            '       Tariff__r.Price_per_kWh__c, Tariff__r.Base_Fee__c ' +
            'FROM Service_Contract__c ' +
            'WHERE Account__c IN :accIds AND Status__c = \'Active\' AND Tariff__c != null';
        Map<String, Object> binds = new Map<String, Object>{ 'accIds' => accountIds };
        for (Service_Contract__c sc :
                (List<Service_Contract__c>) Database.queryWithBinds(contractQuery, binds, AccessLevel.USER_MODE)) {
            contractByAccount.put(sc.Account__c, sc);
        }

        // 2) The consumption profile (the same figures the anomaly action reports).
        Map<Id, HWConsumptionService.Anomaly> consumption =
            HWConsumptionService.anomaliesByAccount(accountIds);

        // 3) The tariff catalogue — ONE query for everyone.
        List<Tariff__c> catalogue = [
            SELECT Id, Name, Type__c, Price_per_kWh__c, Base_Fee__c, CurrencyIsoCode
            FROM   Tariff__c
            WITH   USER_MODE
            ORDER  BY Name
        ];

        for (Id accId : accountIds) {
            out.put(accId, build(contractByAccount.get(accId), consumption.get(accId), catalogue));
        }
        return out;
    }

    /** Assemble one customer's recommendation. Pure — everything is already loaded. */
    private static Recommendation build(Service_Contract__c contract,
                                        HWConsumptionService.Anomaly usage,
                                        List<Tariff__c> catalogue) {
        Recommendation r = new Recommendation();
        r.found = false;

        if (contract == null) {
            r.message = 'I could not find an active contract for this customer, so I cannot '
                + 'compare tariffs. Would you like me to open a case?';
            return r;
        }
        if (usage == null || usage.latestKwh == null) {
            r.message = 'I have no consumption readings for this customer, so I cannot cost the '
                + 'tariffs against their actual usage. I will not guess. Shall I open a case?';
            return r;
        }

        // Only compare like with like: an electricity contract is never costed against a gas tariff.
        String type = contract.Tariff__r.Type__c;
        List<Tariff__c> sameType = new List<Tariff__c>();
        for (Tariff__c t : catalogue) {
            if (t.Type__c == type) sameType.add(t);
        }
        if (sameType.isEmpty()) {
            r.message = 'No comparable tariffs are available for this contract type.';
            return r;
        }

        // The two scenarios the answer genuinely depends on.
        r.baselineKwhMonth = (usage.averageKwh != null) ? usage.averageKwh : usage.latestKwh;
        r.currentKwhMonth  = usage.latestKwh;
        r.anomalyPresent   = (usage.anomalyPercent != null && usage.anomalyPercent >= 30);

        List<TariffCost> atBaseline = rank(sameType, r.baselineKwhMonth * MONTHS);
        List<TariffCost> atCurrent  = rank(sameType, r.currentKwhMonth  * MONTHS);

        r.currentTariffId   = contract.Tariff__c;
        r.currentTariffName = contract.Tariff__r.Name;
        r.currencyIso       = atBaseline[0].currencyIso;
        r.currentAnnualAtBaseline = annualCost(
            contract.Tariff__r.Price_per_kWh__c, contract.Tariff__r.Base_Fee__c,
            r.baselineKwhMonth * MONTHS);
        r.currentAnnualAtCurrent = annualCost(
            contract.Tariff__r.Price_per_kWh__c, contract.Tariff__r.Base_Fee__c,
            r.currentKwhMonth * MONTHS);

        TariffCost bestBase = atBaseline[0];
        TariffCost bestCurr = atCurrent[0];

        r.bestAtBaselineId    = bestBase.tariffId;
        r.bestAtBaselineName  = bestBase.tariffName;
        r.bestAnnualAtBaseline = bestBase.annualCost;
        r.savingAtBaseline    = (r.currentAnnualAtBaseline - bestBase.annualCost).setScale(2);

        r.bestAtCurrentId     = bestCurr.tariffId;
        r.bestAtCurrentName   = bestCurr.tariffName;
        r.bestAnnualAtCurrent = bestCurr.annualCost;
        r.savingAtCurrent     = (r.currentAnnualAtCurrent - bestCurr.annualCost).setScale(2);

        // THE point: if the cheapest tariff differs between the two scenarios, the honest
        // answer is conditional — the agent must name the fact it does not know.
        r.isConditional = (bestBase.tariffId != bestCurr.tariffId);

        if (r.isConditional) {
            r.assumptionBasis = 'The recommendation depends on whether the higher usage is '
                + 'permanent. At the customer\'s historical average of ' + r.baselineKwhMonth
                + ' kWh/month, ' + bestBase.tariffName + ' is cheapest. If the recent '
                + r.currentKwhMonth + ' kWh/month is the new normal (for example a wallbox or '
                + 'heat pump), ' + bestCurr.tariffName + ' becomes cheapest instead — it has a '
                + 'lower price per kWh but a higher monthly base fee. Ask the customer whether '
                + 'the new load is permanent before recommending a switch.';
        } else {
            r.assumptionBasis = bestBase.tariffName + ' is the cheapest tariff in BOTH scenarios '
                + '(at the historical ' + r.baselineKwhMonth + ' kWh/month and at the recent '
                + r.currentKwhMonth + ' kWh/month), so the recommendation does not depend on '
                + 'whether the higher usage persists.';
        }

        r.comparison = buildComparison(atBaseline, atCurrent, r);
        r.citation   = 'HanseWatt Tariff catalogue (Tariff__c) x the customer\'s own meter readings';
        r.found      = true;
        return r;
    }

    /** A quotable table: every tariff, costed in both scenarios. */
    private static String buildComparison(List<TariffCost> atBaseline,
                                          List<TariffCost> atCurrent,
                                          Recommendation r) {
        Map<Id, Decimal> currentById = new Map<Id, Decimal>();
        for (TariffCost c : atCurrent) currentById.put(c.tariffId, c.annualCost);

        String cur = (r.currencyIso == null) ? '' : ' ' + r.currencyIso;
        List<String> lines = new List<String>();
        lines.add('Annual cost at ' + r.baselineKwhMonth + ' kWh/month (historical average) '
            + 'vs at ' + r.currentKwhMonth + ' kWh/month (if the higher usage persists):');
        for (TariffCost c : atBaseline) {
            lines.add('- ' + c.tariffName
                + ' (' + c.pricePerKwh + '/kWh + ' + c.baseFeeMonthly + '/month base fee): '
                + c.annualCost + cur + ' | ' + currentById.get(c.tariffId) + cur
                + (c.tariffId == r.currentTariffId ? '   <- current tariff' : ''));
        }
        return String.join(lines, '\n');
    }

    public class HWTariffException extends Exception {}
}