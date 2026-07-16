public without sharing class SubqueryDemo {
    public static List<Account> run() {
        // A multiline SOQL with a subquery: regex grabs the inner FROM.
        return [
            SELECT Id, Name, (SELECT LastName FROM Contacts)
            FROM Account
            WHERE Name != null
        ];
    }
}
