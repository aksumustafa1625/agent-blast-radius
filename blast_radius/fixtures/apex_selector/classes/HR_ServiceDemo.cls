public with sharing class HR_ServiceDemo {
    @InvocableMethod(label='Get IBAN summary')
    public static List<String> run(List<String> ids) {
        return new HR_SelectorDemo().getIbans();
    }
}
