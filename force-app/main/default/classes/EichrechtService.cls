/**
 * @description  The Eichrecht decision engine. Takes a charge point and its event log, walks the
 *               events in order, and returns a DecisionResult carrying the answer, the German
 *               reasoning, and the provisions the answer rests on.
 *
 *               This class exists because the declarative layer cannot see chronology. A formula
 *               can read the latest calibration and add eight years. It cannot ask whether that
 *               calibration was already late, which is the question § 34 Abs. 1 Satz 3 MessEV
 *               answers with a backdating penalty — and taking the favourable branch by default is
 *               wrong in the dangerous direction, because it grants protection the statute
 *               withholds. `Ladepunkt__c.Eichstatus__c` stays as the list-view answer and is
 *               deliberately not deleted: a reviewer sees compliance state without running
 *               anything. Where the two differ, this class is the authority.
 *
 *               Two ordering rules are decisions rather than arithmetic, so they are stated here.
 *               A later Nacheichung cures an earlier early termination, because re-calibration is
 *               exactly what § 37 Abs. 2 Nr. 2 leaves the operator to do. A blocking software
 *               update is not cured by anything except the authority's approval, because § 37
 *               Abs. 6 ties the block to that approval and to nothing else.
 *
 * @group        VoltStream Channel Partner Management
 * @author       Mustafa Aksu
 * @date         2026-08-23
 */
public with sharing class EichrechtService {

    /**
     * @description  Eichrecht status of one charge point today.
     * @param  ladepunkt  The charge point; may be null.
     * @param  eingriffe  Its events; may be null or empty.
     * @return  The decision, never null.
     */
    public static DecisionResult bewerteEichfrist(Ladepunkt__c ladepunkt, List<Eingriff__c> eingriffe) {
        return bewerteEichfrist(ladepunkt, eingriffe, Date.today());
    }

    /**
     * @description  Eichrecht status of one charge point on a chosen day. The Stichtag is a
     *               parameter and not `TODAY()` so the same facts always produce the same answer:
     *               a test can assert an expiry without waiting for a year to pass, and an audit
     *               can reproduce what the engine said last March.
     * @param  ladepunkt  The charge point; may be null.
     * @param  eingriffe  Its events; may be null or empty.
     * @param  stichtag   The day the answer is asserted for; may be null, treated as today.
     * @return  The decision, never null.
     */
    public static DecisionResult bewerteEichfrist(Ladepunkt__c ladepunkt,
                                                  List<Eingriff__c> eingriffe,
                                                  Date stichtag) {
        Date tag = (stichtag == null) ? Date.today() : stichtag;
        if (ladepunkt == null) {
            return new DecisionResult(DecisionResult.Status.UNBEKANNT, tag)
                .begruende('Es wurde kein Ladepunkt übergeben.');
        }

        Fristlage lage = laufeChronologie(ladepunkt, eingriffe);

        // § 37 Abs. 6: the period is expressly untouched, and the device still may not run. This
        // outranks the period question rather than competing with it, so it is answered first and
        // does not need the dates to be known.
        if (lage.gesperrt) {
            DecisionResult r = ergebnis(DecisionResult.Status.BETRIEB_GESPERRT, tag, lage)
                .begruende('Ein Software-Update wartet auf die Freigabe durch die Eichbehörde. '
                         + 'Die Eichfrist bleibt davon unberührt, der Ladepunkt darf bis zur '
                         + 'Freigabe dennoch nicht betrieben werden.');
            return lage.ende == null ? r
                 : r.begruende('Die Eichfrist selbst läuft bis zum ' + DateUtils.deutsch(lage.ende) + '.');
        }

        if (lage.ende == null) {
            return new DecisionResult(DecisionResult.Status.UNBEKANNT, tag)
                .begruende('Der Fristbeginn lässt sich nicht bestimmen: es fehlt sowohl ein Datum '
                         + 'des Inverkehrbringens als auch eine datierte Nacheichung. Das ist '
                         + 'keine Unbedenklichkeitsbescheinigung, sondern eine Datenlücke.');
        }

        // § 37 Abs. 2 Nr. 2: an intervention ended the period early and no calibration followed.
        if (lage.vorzeitigBeendet) {
            return ergebnis(DecisionResult.Status.VORZEITIG_BEENDET, tag, lage)
                .begruende('Am ' + DateUtils.deutsch(lage.beendetAm) + ' wurde ein Eingriff vorgenommen, der '
                         + 'die messtechnischen Eigenschaften beeinflussen kann. Die Eichfrist ist '
                         + 'damit vorzeitig beendet; eine spätere Nacheichung liegt nicht vor.');
        }

        if (tag <= lage.ende) {
            return ergebnis(DecisionResult.Status.GUELTIG, tag, lage)
                .begruende('Die Eichfrist läuft am ' + DateUtils.deutsch(tag) + ' noch und endet am '
                         + DateUtils.deutsch(lage.ende) + '.');
        }

        return bewerteNachAblauf(ladepunkt, tag, lage);
    }

    /**
     * @description  The § 38 MessEG question on its own: is this device covered by the rules on
     *               late calibration at all, and if so, is it protected?
     *
     *               Kept separate from the status ladder because it is the clearest place in the
     *               domain where "the provision does not apply" and "we cannot tell" are different
     *               answers, and both are different from "no". A device whose period still runs is
     *               outside § 38 entirely — reporting that as "not protected" would state
     *               something the statute does not.
     * @param  ladepunkt  The charge point; may be null.
     * @param  eingriffe  Its events; may be null or empty.
     * @param  stichtag   The day the answer is asserted for; may be null, treated as today.
     * @return  NICHT_ANWENDBAR, UNBEKANNT, GESCHUETZT, ERMESSEN or ABGELAUFEN.
     */
    public static DecisionResult pruefeVerspaeteteEichung(Ladepunkt__c ladepunkt,
                                                          List<Eingriff__c> eingriffe,
                                                          Date stichtag) {
        Date tag = (stichtag == null) ? Date.today() : stichtag;
        if (ladepunkt == null) {
            return new DecisionResult(DecisionResult.Status.UNBEKANNT, tag)
                .begruende('Es wurde kein Ladepunkt übergeben.');
        }

        Fristlage lage = laufeChronologie(ladepunkt, eingriffe);
        if (lage.ende == null) {
            return new DecisionResult(DecisionResult.Status.UNBEKANNT, tag)
                .begruende('Ohne bestimmbaren Fristbeginn lässt sich nicht sagen, ob die Frist '
                         + 'abgelaufen ist.');
        }

        if (tag <= lage.ende) {
            return ergebnis(DecisionResult.Status.NICHT_ANWENDBAR, tag, lage)
                .zitiere('MessEG_38_1')
                .begruende('§ 38 MessEG regelt verspätete Eichungen. Die Eichfrist läuft am '
                         + DateUtils.deutsch(tag) + ' noch bis zum ' + DateUtils.deutsch(lage.ende) + ', die '
                         + 'Vorschrift ist auf diesen Ladepunkt daher nicht anwendbar. Das ist '
                         + 'ausdruecklich keine Aussage darueber, ob er geschuetzt wäre.');
        }

        return bewerteNachAblauf(ladepunkt, tag, lage);
    }

    /**
     * @description  Eichrecht status for many charge points at once, loading through the Selector.
     *               The bulk entry point the invocable action and the LWC card will use.
     * @param  ladepunktIds  Ids to evaluate; null or empty yields an empty map.
     * @param  stichtag      The day the answers are asserted for; may be null, treated as today.
     * @return  One decision per Id that was found.
     */
    public static Map<Id, DecisionResult> bewerteEichfrist(Set<Id> ladepunktIds, Date stichtag) {
        Map<Id, DecisionResult> ergebnisse = new Map<Id, DecisionResult>();
        List<Ladepunkt__c> ladepunkte = LadepunktSelector.byIds(ladepunktIds);
        if (ladepunkte.isEmpty()) {
            return ergebnisse;
        }

        Map<Id, List<Eingriff__c>> jeLadepunkt = new Map<Id, List<Eingriff__c>>();
        for (Eingriff__c e : LadepunktSelector.eingriffeByLadepunkt(ladepunktIds)) {
            if (!jeLadepunkt.containsKey(e.Ladepunkt__c)) {
                jeLadepunkt.put(e.Ladepunkt__c, new List<Eingriff__c>());
            }
            jeLadepunkt.get(e.Ladepunkt__c).add(e);
        }

        for (Ladepunkt__c lp : ladepunkte) {
            ergebnisse.put(lp.Id, bewerteEichfrist(lp, jeLadepunkt.get(lp.Id), stichtag));
        }
        return ergebnisse;
    }

    // ─────────────────────────────────────────────────────────────────────────────────────────

    /** State of the calibration period after walking every event, plus the norms that applied. */
    private class Fristlage {
        Date beginn;
        Date ende;
        Boolean vorzeitigBeendet = false;
        Date beendetAm;
        Boolean gesperrt = false;
        Boolean erstfristUnbestimmt = false;
        List<String> normen = new List<String>();

        void zitiere(String schluessel) {
            if (!normen.contains(schluessel)) {
                normen.add(schluessel);
            }
        }
    }

    /**
     * Replays the event log in order. Everything that needs to know which event came first lives
     * here; everything downstream reads a finished Fristlage.
     */
    private static Fristlage laufeChronologie(Ladepunkt__c lp, List<Eingriff__c> eingriffe) {
        Fristlage lage = new Fristlage();

        if (lp.Inverkehrbringen__c != null) {
            lage.beginn = lp.Inverkehrbringen__c;
            lage.ende = DateUtils.fristende(lage.beginn, DateUtils.EICHFRIST_LADEPUNKT_JAHRE);
            lage.zitiere('MessEG_37_1_2');
        } else {
            // Not fatal. § 34 Abs. 1 Satz 2 can open a period from a calibration alone - but then
            // no previous period exists to test lateness against, and the walk records that.
            lage.erstfristUnbestimmt = true;
        }

        for (Eingriff__c e : chronologisch(eingriffe)) {
            if (e.Typ__c == 'Nacheichung') {
                Date vorherigesEnde = lage.ende;
                Boolean zuSpaet = vorherigesEnde != null && e.Datum__c > vorherigesEnde;
                Boolean stilllegungBelegt = (e.Stilllegung_nachgewiesen__c == true);

                lage.beginn = DateUtils.fristbeginnNachEichung(
                    e.Datum__c, vorherigesEnde, e.Stilllegung_nachgewiesen__c);
                lage.ende = DateUtils.fristende(lage.beginn, DateUtils.EICHFRIST_LADEPUNKT_JAHRE);

                lage.zitiere(!zuSpaet ? 'MessEV_34_1_2'
                                      : (stilllegungBelegt ? 'MessEV_34_1_4' : 'MessEV_34_1_3'));

                // A calibration is precisely the remedy § 37 Abs. 2 Nr. 2 leaves open, so it
                // clears an earlier early termination. It does not clear a § 37 Abs. 6 block:
                // that one ends with the authority's approval and with nothing else.
                lage.vorzeitigBeendet = false;
                lage.beendetAm = null;
                continue;
            }

            if (e.Beendet_Eichfrist__c == true) {
                lage.vorzeitigBeendet = true;
                lage.beendetAm = e.Datum__c;
                lage.zitiere('MessEG_37_2_2');
            }
            if (e.Sperrt_Betrieb__c == true) {
                lage.gesperrt = true;
                lage.zitiere('MessEG_37_6');
            }
        }

        if (lage.ende != null) {
            lage.zitiere('MessEV_Anlage7_Tab1_Nr6_7');
            lage.zitiere('MessEV_34_2');
        }
        return lage;
    }

    /** The § 38 ladder, shared by both public entry points so they cannot disagree. */
    private static DecisionResult bewerteNachAblauf(Ladepunkt__c lp, Date tag, Fristlage lage) {
        Date antrag = lp.Nacheichung_beantragt_am__c;

        if (DateUtils.istAntragRechtzeitig(antrag, lage.ende)) {
            return ergebnis(DecisionResult.Status.GESCHUETZT, tag, lage)
                .zitiere('MessEG_38_1')
                .begruende('Die Eichfrist ist am ' + DateUtils.deutsch(lage.ende) + ' abgelaufen, die '
                         + 'erneute Eichung wurde aber am ' + DateUtils.deutsch(antrag) + ' und damit '
                         + 'mindestens zehn Wochen vorher beantragt. Der Ladepunkt steht bis zur '
                         + 'behördlichen Überprüfung einem geeichten Messgerät gleich. § 38 '
                         + 'verlangt zusätzlich, dass der Verwender das seinerseits Erforderliche '
                         + 'getan oder angeboten hat; das ist eine Wertung und hier nicht geprüft.');
        }

        if (antrag != null) {
            return ergebnis(DecisionResult.Status.ERMESSEN, tag, lage)
                .zitiere('MessEG_38_2')
                .begruende('Die Eichfrist ist am ' + DateUtils.deutsch(lage.ende) + ' abgelaufen. Der Antrag '
                         + 'vom ' + DateUtils.deutsch(antrag) + ' kam später als zehn Wochen vor Ablauf, '
                         + 'daher besteht kein Anspruch auf Weiterverwendung. Die Behörde kann '
                         + 'sie gestatten - kann, nicht muss.');
        }

        return ergebnis(DecisionResult.Status.ABGELAUFEN, tag, lage)
            .begruende('Die Eichfrist ist am ' + DateUtils.deutsch(lage.ende) + ' abgelaufen und eine '
                     + 'erneute Eichung wurde nicht beantragt.');
    }

    /** Builds a result carrying the dates and every norm the walk actually applied. */
    private static DecisionResult ergebnis(DecisionResult.Status wert, Date tag, Fristlage lage) {
        DecisionResult r = new DecisionResult(wert, tag);
        r.fristbeginn = lage.beginn;
        r.fristende = lage.ende;
        for (String schluessel : lage.normen) {
            r.zitiere(schluessel);
        }
        if (lage.erstfristUnbestimmt) {
            r.begruende('Hinweis: das Inverkehrbringen ist nicht erfasst, die erste Eichfrist '
                      + 'ließ sich daher nicht bestimmen. Ob eine Nacheichung verspätet war, '
                      + 'konnte nicht geprüft werden - die günstigere Auslegung wurde gewählt.');
        }
        return r;
    }

    /**
     * Undated events are dropped: an event without a date cannot be placed in a chronology, and
     * guessing a position for it would be worse than ignoring it. Where two events share a date,
     * a Nacheichung sorts last, so a calibration recorded on the same day as an intervention is
     * read as curing it. That is a judgement, not arithmetic: the opposite order would leave a
     * freshly calibrated device reported as terminated.
     */
    private static List<Eingriff__c> chronologisch(List<Eingriff__c> eingriffe) {
        List<Eingriff__c> sortiert = new List<Eingriff__c>();
        if (eingriffe == null) {
            return sortiert;
        }
        List<Ereignis> gereiht = new List<Ereignis>();
        for (Eingriff__c e : eingriffe) {
            if (e.Datum__c != null) {
                gereiht.add(new Ereignis(e));
            }
        }
        gereiht.sort();
        for (Ereignis ev : gereiht) {
            sortiert.add(ev.eingriff);
        }
        return sortiert;
    }

    private class Ereignis implements Comparable {
        Eingriff__c eingriff;
        Ereignis(Eingriff__c eingriff) {
            this.eingriff = eingriff;
        }
        public Integer compareTo(Object anderes) {
            Ereignis other = (Ereignis) anderes;
            if (eingriff.Datum__c != other.eingriff.Datum__c) {
                return eingriff.Datum__c > other.eingriff.Datum__c ? 1 : -1;
            }
            Integer a = eingriff.Typ__c == 'Nacheichung' ? 1 : 0;
            Integer b = other.eingriff.Typ__c == 'Nacheichung' ? 1 : 0;
            return a - b;
        }
    }
}