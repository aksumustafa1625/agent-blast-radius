/**
 * @description  Every query against Ladepunkt__c and its Eingriff__c children. Handlers, helpers
 *               and services do not inline SOQL, so when a field is added to the compliance
 *               calculation exactly one file changes.
 *
 *               Events come back ordered by date because EichrechtService walks them as a
 *               chronology. The service sorts defensively anyway — it also accepts lists that
 *               never passed through here — but a Selector that hands back an arbitrary order for
 *               data whose meaning is its order would be setting a trap.
 *
 * @group        VoltStream Channel Partner Management
 * @author       Mustafa Aksu
 * @date         2026-08-23
 */
public with sharing class LadepunktSelector {

    /**
     * @description  Charge points by Id, with every field the Eichrecht calculation reads.
     * @param  ladepunktIds  Ids to load; null or empty yields an empty list.
     * @return  Matching charge points.
     */
    public static List<Ladepunkt__c> byIds(Set<Id> ladepunktIds) {
        if (ladepunktIds == null || ladepunktIds.isEmpty()) {
            return new List<Ladepunkt__c>();
        }
        return [
            SELECT Id, Name, Inverkehrbringen__c, Nacheichung_beantragt_am__c,
                   Ladeleistung_kW__c, Oeffentlich_zugaenglich__c, Standort_Adresse__c,
                   Eichstatus__c, Fristbeginn__c, Eichfrist_Ende__c
            FROM Ladepunkt__c
            WHERE Id IN :ladepunktIds
            WITH USER_MODE
            LIMIT 50000
        ];
    }

    /**
     * @description  A locator over every charge point, for the nightly sweep.
     *
     *               A QueryLocator rather than a list because a batch has to stream: a fleet
     *               imported over OCPI is not a handful of records, and a method returning
     *               List<Ladepunkt__c> would put the whole estate in one heap. It still lives here
     *               rather than in the batch, so the rule holds — every query against this object
     *               is in this file, and adding a field the sweep needs changes one place.
     * @return  Locator over all charge points, oldest first.
     */
    public static Database.QueryLocator alleFuerPruefung() {
        return Database.getQueryLocator([
            SELECT Id, Name, Eichstatus__c, Inverkehrbringen__c, Nacheichung_beantragt_am__c
            FROM Ladepunkt__c
            ORDER BY CreatedDate ASC
        ]);
    }

    /**
     * @description  Charge points by their auto-number, for a caller who has a name rather than an
     *               Id — which is every caller that came from a sentence a human typed.
     * @param  nummer  The record name, e.g. LP-00007. Whitespace is normalised; SOQL string
     *                 comparison is already case-insensitive, so no case handling is needed here.
     *
     *                 Deliberately does NOT select the operator's name. Nothing on this path reads
     *                 it, and under WITH USER_MODE a cross-object field drags that object's
     *                 permissions into the dependency - which is how a working agent began
     *                 answering "status cannot be determined" for a charge point whose status was
     *                 perfectly determinable. Select what you use.
     * @return  Matching charge points; empty when the input is blank or nothing matches.
     */
    public static List<Ladepunkt__c> byName(String nummer) {
        String gesucht = StringUtils.normalizeWhitespace(nummer);
        if (String.isBlank(gesucht)) {
            return new List<Ladepunkt__c>();
        }
        return [
            SELECT Id, Name, Inverkehrbringen__c, Nacheichung_beantragt_am__c,
                   Ladeleistung_kW__c, Oeffentlich_zugaenglich__c, Standort_Adresse__c,
                   Eichstatus__c, Fristbeginn__c, Eichfrist_Ende__c
            FROM Ladepunkt__c
            WHERE Name = :gesucht
            WITH USER_MODE
            LIMIT 50000
        ];
    }

    /**
     * @description  Every charge point of one operator, matched on a fragment of the account name.
     *               A fragment rather than an exact match because the caller is quoting a person:
     *               somebody asks about "Stadtwerke Muenchen" and the account is registered as
     *               "Stadtwerke Muenchen GmbH". The fragment is a bind variable, so widening the
     *               match does not widen the injection surface.
     *
     *                Filters on the denormalised formula rather than traversing Betreiber__r,
     *                because a relationship in a WHERE clause needs read access to the whole
     *                target object while a cross-object formula is evaluated in system context.
     *                The agent runs as a service user; handing it Account access to answer a
     *                question about charge points is a grant nobody should have to make.
     * @param  betreiber  Part of the operator's account name.
     * @return  Matching charge points; empty when the input is blank or nothing matches.
     */
    public static List<Ladepunkt__c> byBetreiberName(String betreiber) {
        String gesucht = StringUtils.normalizeWhitespace(betreiber);
        if (String.isBlank(gesucht)) {
            return new List<Ladepunkt__c>();
        }
        String muster = '%' + gesucht + '%';
        return [
            SELECT Id, Name, Inverkehrbringen__c, Nacheichung_beantragt_am__c,
                   Ladeleistung_kW__c, Oeffentlich_zugaenglich__c, Standort_Adresse__c,
                   Eichstatus__c, Fristbeginn__c, Eichfrist_Ende__c, Betreiber_Name__c
            FROM Ladepunkt__c
            WHERE Betreiber_Name__c LIKE :muster
            WITH USER_MODE
            ORDER BY Name ASC
            LIMIT 50000
        ];
    }

    /**
     * @description  Every event belonging to the given charge points, oldest first.
     * @param  ladepunktIds  Parent Ids; null or empty yields an empty list.
     * @return  Events ordered by date, then by type so a calibration sorts after an intervention
     *          that shares its date — see EichrechtService for why that order is the safe one.
     */
    public static List<Eingriff__c> eingriffeByLadepunkt(Set<Id> ladepunktIds) {
        if (ladepunktIds == null || ladepunktIds.isEmpty()) {
            return new List<Eingriff__c>();
        }
        return [
            SELECT Id, Ladepunkt__c, Typ__c, Datum__c, Beschreibung__c,
                   Beendet_Eichfrist__c, Sperrt_Betrieb__c, Nacheichungsantrag_offen__c,
                   Stilllegung_nachgewiesen__c, Behoerdliche_Freigabe_am__c,
                   Instandsetzer_befugt__c, Nacheichung_beantragt__c,
                   Kennzeichnung_41__c, Behoerde_informiert__c
            FROM Eingriff__c
            WHERE Ladepunkt__c IN :ladepunktIds
            WITH USER_MODE
            ORDER BY Datum__c ASC NULLS LAST
            LIMIT 50000
        ];
    }
}