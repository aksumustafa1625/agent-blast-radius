/**
 * @description  Stateless date arithmetic for the German Eichrecht. Each public method
 *               answers exactly one sentence of § 34 MessEV or § 38 MessEG and nothing
 *               else — no SOQL, no DML, no sObjects — so the test table can be read
 *               beside the statute, row for row.
 *
 *               Null contract, matching StringUtils: missing data in -> null or the
 *               harsher answer out. A non-null argument outside the statute's range is a
 *               programming error, not missing data, and throws.
 *
 * @group        VoltStream Channel Partner Management
 * @author       Mustafa Aksu
 * @date         2026-08-23
 */
public with sharing class DateUtils {

    /**
     * § 34 Abs. 1 Satz 1 MessEV. Two years is the statutory default and applies
     * "soweit nicht etwas anderes" is prescribed. Charge points are that etwas anderes.
     */
    public static final Integer EICHFRIST_STANDARD_JAHRE = 2;

    /**
     * MessEV Anlage 7 Tabelle 1 Nr. 6.7 — one entry covering AC and DC alike, which is why
     * the two are identical. Eight is a table value, not a property of charge points, and
     * it moves into Rechtsnorm__mdt with validity dates once the corpus exists.
     */
    public static final Integer EICHFRIST_LADEPUNKT_JAHRE = 8;

    /** § 38 Satz 1 MessEG: "mindestens zehn Wochen vor Ablauf der Eichfrist". */
    public static final Integer ANTRAGSFRIST_TAGE = 70;

    /**
     * @description  A date in German notation, independent of who is logged in. `Date.format()`
     *               follows the running user's locale, so a German sentence assembled with it
     *               reads "8/23/2026" for an English-locale user — and the engine's Begruendung is
     *               not only painted on a card, it is the text the agent narrates. A locale
     *               deciding how German legal prose reads is a defect, not a preference.
     *
     *               Deviates from the null contract on purpose: a null here would concatenate into
     *               a sentence as the word "null", so it yields the German word instead.
     * @param  wert  The date; may be null.
     * @return  'TT.MM.JJJJ', or 'unbekannt' when the date is missing.
     */
    public static String deutsch(Date wert) {
        if (wert == null) {
            return 'unbekannt';
        }
        return String.valueOf(wert.day()).leftPad(2, '0') + '.'
             + String.valueOf(wert.month()).leftPad(2, '0') + '.'
             + String.valueOf(wert.year());
    }

    /**
     * @description  End of a calibration period. Two provisions combine: § 34 Abs. 1 MessEV
     *               gives the arithmetic end, then § 34 Abs. 2 moves it to the end of that
     *               calendar year — but only for periods of at least one year. That is a
     *               condition, not a universal rule; shorter periods fall under Abs. 3 and
     *               end at month's end instead. They are rejected here rather than silently
     *               mishandled, because no charge-point Eichfrist is shorter than a year.
     * @param  fristbeginn  Start of the period; may be null.
     * @param  jahre        Length in whole years; must be at least 1.
     * @return  31 December of the year the period runs out, or null when the start is unknown.
     */
    public static Date fristende(Date fristbeginn, Integer jahre) {
        if (fristbeginn == null || jahre == null) {
            return null;
        }
        if (jahre < 1) {
            throw new IllegalArgumentException(
                'Eichfristen unter einem Jahr fallen unter § 34 Abs. 3 MessEV (Monatsende) ' +
                'und werden hier nicht berechnet.');
        }
        // Whether the arithmetic end sits on the anniversary or the day before it is a § 188
        // BGB question that cannot change the answer: both readings land in the same calendar
        // year, and Abs. 2 reads nothing but the year.
        return Date.newInstance(fristbeginn.addYears(jahre).year(), 12, 31);
    }

    /**
     * @description  Start of the NEXT period after a Nacheichung — § 34 Abs. 1 Sätze 2 to 4
     *               MessEV, where the order of the sentences is the whole rule:
     *               Satz 2 — calibrated while the period still ran: the Tag der Eichung governs.
     *               Satz 3 — calibrated after it expired: the new period is backdated to the
     *                        END of the old one, so the lateness is deducted from the next term.
     *               Satz 4 — the only escape from Satz 3: a device "nachweislich länger als ein
     *                        Jahr nicht verwendet" gets the Tag der Eichung back.
     *               Satz 4 is relief from Satz 3 rather than an independent branch, which is why
     *               the dormancy claim is consulted only once lateness has been established.
     * @param  eichungsdatum            Day the device was calibrated; may be null.
     * @param  vorherigesFristende      End of the period before it; null when there was none.
     * @param  stilllegungNachgewiesen  Whether dormancy beyond a year is PROVEN. Null is read as
     *                                  false: nachweislich puts the burden on the operator, so an
     *                                  absent claim is the harsher answer and not a gap.
     * @return  Start of the new period, or null when the calibration date is unknown.
     */
    public static Date fristbeginnNachEichung(Date eichungsdatum,
                                              Date vorherigesFristende,
                                              Boolean stilllegungNachgewiesen) {
        if (eichungsdatum == null) {
            return null;
        }
        if (vorherigesFristende == null || eichungsdatum <= vorherigesFristende) {
            return eichungsdatum;
        }
        return (stilllegungNachgewiesen == true) ? eichungsdatum : vorherigesFristende;
    }

    /**
     * @description  Whether a Nacheichung was applied for early enough to earn the automatic
     *               protection of § 38 Satz 1 MessEG — "mindestens zehn Wochen vor Ablauf der
     *               Eichfrist". Crossing that line is not a breach: it drops the operator into
     *               Satz 2, where continued use is at the authority's discretion ("kann"). So a
     *               false here means "no entitlement", never "unlawful".
     *
     *               One limit worth naming rather than discovering later: Satz 1 also requires
     *               the Verwender to have done or offered "das zur Eichung seinerseits
     *               Erforderliche". That is a judgement, not a date, and this method neither
     *               tests it nor pretends to.
     * @param  antragsdatum  Date the re-calibration was applied for; may be null.
     * @param  fristende     End of the current period; may be null.
     * @return  True only when both dates are known and the application beat the ten-week line.
     *          Missing data yields false, because protection has to be earned, not assumed.
     */
    public static Boolean istAntragRechtzeitig(Date antragsdatum, Date fristende) {
        if (antragsdatum == null || fristende == null) {
            return false;
        }
        return antragsdatum <= fristende.addDays(-ANTRAGSFRIST_TAGE);
    }
}