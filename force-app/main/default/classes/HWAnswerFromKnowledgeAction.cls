/**
 * HWAnswerFromKnowledgeAction — the Agentforce-callable action that answers a *procedure*
 * question ("I'm moving house, what do I need to do?", "what happens during an outage?")
 * from a cited HanseWatt Knowledge article.
 *
 * This is the other half of the grounding split (ADR-007):
 *   figures    -> Data 360 / billing records   (HWExplainConsumptionAction, HWGetLatestBillAction)
 *   procedure  -> Knowledge, with a citation   (this action)
 *
 * The agent must answer from the returned article text and quote the citation; if no article
 * matches, the action says so honestly rather than letting the model improvise a policy.
 *
 * Bulk-safe @InvocableMethod delegating to HWKnowledgeService (ADR-006).
 */
public with sharing class HWAnswerFromKnowledgeAction {

    public class Request {
        @InvocableVariable(
            label='Question'
            description='The customer\'s procedural question, or the key topic words to look up. Prefer English topic words (e.g. "moving house umzug", "power outage", "payment methods", "cancel contract"); German is also understood.'
            required=true)
        public String question;
    }

    public class Result {
        @InvocableVariable(label='Found') public Boolean found;
        @InvocableVariable(label='Article Title') public String articleTitle;
        @InvocableVariable(label='Article Number') public String articleNumber;
        @InvocableVariable(label='Answer') public String answer;
        @InvocableVariable(label='Citation') public String citation;
        @InvocableVariable(label='Message') public String message;
    }

    @InvocableMethod(
        label='HW Answer From Knowledge'
        description='Answers a procedural/how-to question (moving house, power outage, payment methods, tariff change, cancellation, smart meter readings) from a cited HanseWatt Knowledge article. Use this for policy and process questions; use the consumption and bill actions for figures.')
    public static List<Result> run(List<Request> requests) {
        List<String> questions = new List<String>();
        for (Request req : requests) {
            if (String.isNotBlank(req.question)) {
                questions.add(req.question);
            }
        }
        Map<String, HWKnowledgeService.Article> byQuestion =
            HWKnowledgeService.bestArticleByQuestion(questions);

        List<Result> results = new List<Result>();
        for (Request req : requests) {
            Result res = new Result();
            HWKnowledgeService.Article a =
                String.isNotBlank(req.question) ? byQuestion.get(req.question) : null;
            if (a != null) {
                res.found         = true;
                res.articleTitle  = a.title;
                res.articleNumber = a.articleNumber;
                res.answer        = a.summary;
                res.citation      = a.citation;
                res.message       = 'Answer this from the article text and cite it: ' + a.citation;
            } else {
                res.found    = false;
                res.citation = '';
                res.message  = 'No HanseWatt help article covers that question. Do not guess the '
                    + 'policy — offer to open a case so a specialist can answer.';
            }
            results.add(res);
        }
        return results;
    }
}