/**
 * @description  The Eichrecht check as an invocable action — what the agent is allowed to call
 *               when someone asks about calibration deadlines.
 *
 *               The division of labour this whole project rests on is enforced here rather than
 *               asserted: the action decides nothing. It resolves which charge points the question
 *               is about, hands them to EichrechtService, and returns the engine's German sentences
 *               unchanged. The agent chooses that this action runs and reads the result aloud. It
 *               never computes a deadline, and it cannot, because no deadline arithmetic exists on
 *               this side of the call.
 *
 *               `rechtsgrundlagen` is the load-bearing output. It carries exactly the provisions
 *               the engine applied, and the deterministic transcript gate compares every § the
 *               agent utters against it. A paragraph that is not in this list was not handed over
 *               by the engine — it was invented, and that is a binary rather than a similarity.
 *
 *               Nothing here escapes HTML. Invocable serialisation already escapes, and
 *               String.escapeHtml4 would turn every ü into &uuml; inside text the planner reads.
 *
 * @group        VoltStream Channel Partner Management
 * @author       Mustafa Aksu
 * @date         2026-08-23
 */
public with sharing class PruefeEichfristen {

    /**
     * @description  Check the calibration status of one charge point or of an operator's fleet.
     * @param  anfragen  One request per invocation; the platform bulkifies.
     * @return  One answer per request, in the same order.
     */
    @InvocableMethod(
        label='Eichfristen prüfen'
        description='Prüft den eichrechtlichen Status eines Ladepunkts oder aller Ladepunkte eines Betreibers nach MessEG und MessEV. Liefert je Ladepunkt eine Entscheidung mit Begründung und den Rechtsgrundlagen, auf die sie sich stützt. Berechnet Fristen deterministisch und nicht durch Schätzung.'
        category='Eichrecht')
    public static List<Antwort> pruefe(List<Anfrage> anfragen) {
        List<Antwort> antworten = new List<Antwort>();
        for (Anfrage a : anfragen == null ? new List<Anfrage>() : anfragen) {
            antworten.add(pruefeEine(a));
        }
        return antworten;
    }

    private static Antwort pruefeEine(Anfrage a) {
        Antwort antwort = new Antwort();
        antwort.stichtag = (a.stichtag == null) ? Date.today() : a.stichtag;

        List<Ladepunkt__c> ladepunkte = finde(a);
        if (ladepunkte.isEmpty()) {
            // No invented answer and no cheerful empty state. If nothing matched, the agent is
            // told that nothing matched, so it cannot narrate silence as compliance.
            antwort.zusammenfassung = 'Es wurde kein passender Ladepunkt gefunden.';
            antwort.hinweis = hinweisOhneTreffer(a);
            return antwort;
        }

        Set<Id> ids = new Map<Id, Ladepunkt__c>(ladepunkte).keySet();
        Map<Id, DecisionResult> urteile = EichrechtService.bewerteEichfrist(ids, antwort.stichtag);

        Map<String, Integer> zaehlung = new Map<String, Integer>();
        Set<String> normen = new Set<String>();
        List<String> dringend = new List<String>();
        List<String> unauffaellig = new List<String>();

        for (Ladepunkt__c lp : ladepunkte) {
            DecisionResult d = urteile.get(lp.Id);
            if (d == null) {
                continue;
            }
            String schluessel = String.valueOf(d.ergebnis);
            zaehlung.put(schluessel, (zaehlung.containsKey(schluessel) ? zaehlung.get(schluessel) : 0) + 1);
            normen.addAll(d.rechtsgrundlagen);

            String zeile = befund(lp, d);
            if (HANDLUNGSBEDARF.contains(schluessel)) {
                dringend.add(zeile);
            } else {
                unauffaellig.add(zeile);
            }
        }

        // Findings that need action come first. An agent reads a list top down and a person
        // listening to one hears the first item best, so ordering is part of the answer.
        List<String> alleBefunde = new List<String>(dringend);
        alleBefunde.addAll(unauffaellig);
        antwort.befunde = String.join(alleBefunde, '\n');

        List<String> sortierteNormen = new List<String>(normen);
        sortierteNormen.sort();
        antwort.rechtsgrundlagen = String.join(sortierteNormen, TRENNER);
        antwort.anzahlGeprueft = ladepunkte.size();
        antwort.anzahlHandlungsbedarf = dringend.size();
        antwort.zusammenfassung = zusammenfassung(antwort, zaehlung);
        return antwort;
    }

    private static List<Ladepunkt__c> finde(Anfrage a) {
        if (String.isNotBlank(a.ladepunktNummer)) {
            return LadepunktSelector.byName(a.ladepunktNummer);
        }
        if (String.isNotBlank(a.betreiber)) {
            return LadepunktSelector.byBetreiberName(a.betreiber);
        }
        return new List<Ladepunkt__c>();
    }

    private static String hinweisOhneTreffer(Anfrage a) {
        if (String.isNotBlank(a.ladepunktNummer)) {
            return 'Zur Nummer "' + a.ladepunktNummer + '" existiert kein Ladepunkt. Bitte die '
                 + 'Nummer bestätigen lassen; es darf kein Status genannt werden.';
        }
        if (String.isNotBlank(a.betreiber)) {
            return 'Zum Betreiber "' + a.betreiber + '" ist kein Ladepunkt erfasst. Möglicherweise '
                 + 'ist der Name anders geschrieben; es darf kein Status genannt werden.';
        }
        return 'Es wurde weder eine Ladepunkt-Nummer noch ein Betreiber übergeben. Bitte eines '
             + 'von beidem erfragen.';
    }

    private static String befund(Ladepunkt__c lp, DecisionResult d) {
        String kopf = lp.Name + ' (' + BESCHRIFTUNG.get(String.valueOf(d.ergebnis)) + ')';
        return kopf + ': ' + d.begruendung;
    }

    private static String zusammenfassung(Antwort a, Map<String, Integer> zaehlung) {
        List<String> teile = new List<String>();
        for (String schluessel : REIHENFOLGE) {
            if (zaehlung.containsKey(schluessel)) {
                teile.add(zaehlung.get(schluessel) + ' ' + BESCHRIFTUNG.get(schluessel));
            }
        }
        String satz = a.anzahlGeprueft + ' Ladepunkt' + (a.anzahlGeprueft == 1 ? '' : 'e')
                    + ' geprüft zum ' + DateUtils.deutsch(a.stichtag) + ': '
                    + String.join(teile, ', ') + '.';
        return a.anzahlHandlungsbedarf == 0
            ? satz + ' Kein Handlungsbedarf.'
            : satz + ' ' + a.anzahlHandlungsbedarf + ' davon '
                   + (a.anzahlHandlungsbedarf == 1 ? 'erfordert' : 'erfordern')
                   + ' eine Maßnahme.';
    }

    /**
     * States that need somebody to do something. UNBEKANNT belongs here rather than with the
     * harmless ones: a compliance record with a missing date is not a quiet record, it is an open
     * question, and an agent that files it under "nothing to report" has answered the wrong way.
     */
    private static final Set<String> HANDLUNGSBEDARF = new Set<String>{
        'BETRIEB_GESPERRT', 'VORZEITIG_BEENDET', 'ABGELAUFEN', 'ERMESSEN', 'UNBEKANNT'
    };

    /**
     * Separator for the citation list. A single string rather than a list because Agent Script's
     * action outputs take scalars - list<string> is rejected by the compile service. Nothing is
     * lost: the agent reads the text, and the transcript gate searches it for the paragraphs the
     * agent uttered, which a joined string supports exactly as well as a list did.
     */
    private static final String TRENNER = '; ';

    /** Worst first, so the summary sentence leads with what matters. */
    private static final List<String> REIHENFOLGE = new List<String>{
        'BETRIEB_GESPERRT', 'VORZEITIG_BEENDET', 'ABGELAUFEN', 'ERMESSEN',
        'GESCHUETZT', 'GUELTIG', 'UNBEKANNT', 'NICHT_ANWENDBAR'
    };

    private static final Map<String, String> BESCHRIFTUNG = new Map<String, String>{
        'GUELTIG'           => 'gültig geeicht',
        'GESCHUETZT'        => 'geschützt nach § 38 MessEG',
        'ERMESSEN'          => 'im behördlichen Ermessen nach § 38 MessEG',
        'ABGELAUFEN'        => 'mit abgelaufener Eichfrist',
        'VORZEITIG_BEENDET' => 'mit vorzeitig beendeter Eichfrist',
        'BETRIEB_GESPERRT'  => 'für den Betrieb gesperrt',
        'UNBEKANNT'         => 'ohne bestimmbaren Status',
        'NICHT_ANWENDBAR'   => 'außerhalb des Anwendungsbereichs'
    };

    public class Anfrage {
        @InvocableVariable(
            label='Ladepunkt-Nummer'
            description='Die Nummer eines einzelnen Ladepunkts, zum Beispiel LP-00007. Hat Vorrang vor dem Betreiber.')
        public String ladepunktNummer;

        @InvocableVariable(
            label='Betreiber'
            description='Name des Betreibers oder ein Teil davon, wenn der gesamte Bestand geprüft werden soll.')
        public String betreiber;

        @InvocableVariable(
            label='Stichtag'
            description='Tag, für den die Aussage gelten soll. Leer bedeutet heute. Nur setzen, wenn ausdrücklich nach einem anderen Datum gefragt wurde.')
        public Date stichtag;
    }

    public class Antwort {
        @InvocableVariable(
            label='Zusammenfassung'
            description='Ein deutscher Satz mit dem Gesamtbild. Wörtlich verwendbar.')
        public String zusammenfassung;

        @InvocableVariable(
            label='Befunde'
            description='Je Ladepunkt eine deutsche Zeile mit Entscheidung und Begründung, durch Zeilenumbrüche getrennt. Handlungsbedürftige zuerst.')
        public String befunde = '';

        @InvocableVariable(
            label='Rechtsgrundlagen'
            description='Genau die Vorschriften, auf die sich diese Antwort stützt, durch Semikolon getrennt. Es dürfen ausschließlich diese Paragraphen genannt werden.')
        public String rechtsgrundlagen = '';

        @InvocableVariable(label='Geprüfte Ladepunkte')
        public Integer anzahlGeprueft = 0;

        @InvocableVariable(label='Davon handlungsbedürftig')
        public Integer anzahlHandlungsbedarf = 0;

        @InvocableVariable(
            label='Stichtag'
            description='Der Tag, für den die Aussage gilt.')
        public Date stichtag;

        @InvocableVariable(
            label='Hinweis'
            description='Nur gefüllt, wenn kein Ladepunkt gefunden wurde. Dann darf kein Status genannt werden.')
        public String hinweis;
    }
}