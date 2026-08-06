/**
 * E15/E16 probe: what does a TRIGGER BODY see on the record axis, and why?
 *
 * IT REPORTS TWO NUMBERS, AND THE PAIR IS THE POINT
 *     PLAIN - a SOQL with no mode clause. At v67 the operation defaults to user mode,
 *         so this reads the OPERATION's mode.
 *     SYS   - the same SOQL WITH SYSTEM_MODE. The operation's mode is now fixed, so by
 *         the precedence law the record axis falls to the trigger's AMBIENT SHARING
 *         CONTEXT. This is the only way to observe that context at v67, because a
 *         plain read there is user mode and overrides it.
 *
 * WHAT EACH ANSWERS
 *     PLAIN at v67 = 0  ->  a plain read in a v67 trigger body is bounded (E15)
 *     SYS   at v67 = 5  ->  the ambient context is still WITHOUT sharing, i.e. the
 *                           context did not change; the operation default overrides it
 *     SYS   at v67 = 0  ->  the ambient context itself became with-sharing
 *
 * THE SHAPE THAT MAKES THE NUMBERS MEAN SOMETHING
 *     Blast_Test__c is Private OWD with rows seeded by the ADMIN. The running user has
 *     object READ on it and owns none of those rows, so SHARING is the only thing that
 *     can hide them: not CRUD (granted, and the v58 run proves the read works) and not
 *     FLS (COUNT() touches no field).
 *
 * HOW IT IS RUN - see REPRO_v58_v67.md for the same method
 *     Deployed twice from this one file. The ONLY edit between runs is the number in
 *     the paired .trigger-meta.xml. Same source, same host, same user, same rows.
 */
trigger ShareProbeTrigger on Casc_Parent__c (before insert) {
    Integer plainRows = [SELECT COUNT() FROM Blast_Test__c];
    Integer sysRows   = [SELECT COUNT() FROM Blast_Test__c WITH SYSTEM_MODE];
    Trigger.new[0].addError('PLAIN=' + plainRows + ' SYS=' + sysRows);
}
