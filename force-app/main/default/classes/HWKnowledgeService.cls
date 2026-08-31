/**
 * HWKnowledgeService — the procedure-side retriever of the grounding split (ADR-007):
 * figures come from Data 360 (HWConsumptionService / HWBillingService), *procedure* answers
 * come from a cited Knowledge article. The agent never invents policy, and it never invents
 * the source: this service returns the real article's number + title, which becomes the
 * citation the agent must quote.
 *
 * Why a deterministic retriever instead of the Agentforce Data Library (RAG) index:
 *  - The Data Cloud RAG index for a Data Library cannot be provisioned in this Dev Edition
 *    flavour (it never leaves "Not Started"), and the standard AnswerQuestionsWithKnowledge
 *    action fails without one. See STATUS.md / docs/adr/ADR-007.
 *  - A deterministic retriever is unit-testable for free (no Flex Credits), source-controlled,
 *    and cannot hallucinate a citation. With a 10-article corpus, one query + in-memory
 *    scoring beats a vector index on both cost and explainability.
 *  - A Data Library / vector retriever remains the production path for a large corpus.
 *
 * Standard (ADR-006): with sharing, SOQL WITH USER_MODE, bulk-safe (ONE query regardless of
 * how many questions are asked), no DML.
 */
public with sharing class HWKnowledgeService {

    /** A retrieved, citable help article. */
    public class Article {
        public String  articleNumber;   // e.g. 000001008 — part of the citation
        public String  title;           // e.g. Moving House: Start or Stop Service (Umzug)
        public String  summary;         // the procedural answer text
        public String  urlName;
        public String  citation;        // 'HanseWatt Knowledge — <title> (<articleNumber>)'
        public Integer score;           // keyword-match score; higher = more relevant
    }

    /** Words shorter than this, or in STOP_WORDS, are ignored when scoring. */
    private static final Integer MIN_TOKEN_LENGTH = 3;

    /** A match must beat this score, otherwise we honestly say we found nothing. */
    @TestVisible
    private static final Integer MIN_SCORE = 2;

    private static final Set<String> STOP_WORDS = new Set<String>{
        // English
        'the','and','for','you','your','are','how','what','why','who','can','with','does',
        // German
        'ich','ist','das','die','der','ein','eine','mein','meine','wie','wer','was','muss',
        'bin','mit','von','bei','auf','soll','kann','wenn','habe','haben','tun','mir','nach'
    };

    /**
     * German → English aliases. The agent usually passes English search terms (the action's
     * parameter description asks for them), but a German question can reach us verbatim —
     * so we expand the common DACH service vocabulary onto the English corpus. This keeps
     * retrieval deterministic instead of relying on the model to translate.
     */
    private static final Map<String, String> DE_TO_EN = new Map<String, String>{
        'umzug'        => 'moving',      'umziehe'   => 'moving',    'ziehe'     => 'moving',
        'umziehen'     => 'moving',      'wohnung'   => 'house',
        'stoerung'     => 'outage',      'störung'   => 'outage',    'stromausfall' => 'outage',
        'rechnung'     => 'bill',        'rechnungen'=> 'bill',      'betrag'    => 'bill',
        'tarif'        => 'tariff',      'tarifwechsel' => 'tariff', 'wechsel'   => 'tariff',
        'zahlung'      => 'payment',     'zahlen'    => 'payment',   'bezahlen'  => 'payment',
        'lastschrift'  => 'payment',     'faellig'   => 'payment',   'fällig'    => 'payment',
        'zaehler'      => 'meter',       'zähler'    => 'meter',     'zaehlerstand' => 'meter',
        'verbrauch'    => 'usage',       'strom'     => 'electricity',
        'kuendigung'   => 'cancellation','kündigung' => 'cancellation','kuendigen' => 'cancellation',
        'vertrag'      => 'contract',    'laufzeit'  => 'contract',
        'oekostrom'    => 'green',       'ökostrom'  => 'green',     'gruen'     => 'green',
        'ladestation'  => 'charging',    'elektroauto' => 'charging','hoch'      => 'higher'
    };

    /**
     * Retrieve the best-matching published article for each question.
     * Bulk-safe: ONE SOQL for the whole corpus, then in-memory scoring per question.
     *
     * @param questions the customer questions / search terms (English preferred, German tolerated)
     * @return map of question -> best Article (only questions that matched above MIN_SCORE)
     */
    public static Map<String, Article> bestArticleByQuestion(List<String> questions) {
        Map<String, Article> out = new Map<String, Article>();
        if (questions == null || questions.isEmpty()) {
            return out;
        }

        // ONE query for the whole (small) corpus — bulk-safe by construction.
        List<Knowledge__kav> corpus = [
            SELECT ArticleNumber, Title, Summary, UrlName
            FROM   Knowledge__kav
            WHERE  PublishStatus = 'Online' AND Language = 'en_US'
            WITH   USER_MODE
            LIMIT  200
        ];
        if (corpus.isEmpty()) {
            return out;
        }

        for (String q : questions) {
            if (String.isBlank(q)) {
                continue;
            }
            Article best = null;
            Set<String> tokens = tokenize(q);
            for (Knowledge__kav k : corpus) {
                Integer score = scoreArticle(k, tokens);
                if (score >= MIN_SCORE && (best == null || score > best.score)) {
                    best = toArticle(k, score);
                }
            }
            if (best != null) {
                out.put(q, best);
            }
        }
        return out;
    }

    /** Split a question into meaningful, lower-cased tokens, expanding German → English. */
    @TestVisible
    private static Set<String> tokenize(String question) {
        Set<String> tokens = new Set<String>();
        if (String.isBlank(question)) {
            return tokens;
        }
        for (String raw : question.toLowerCase().split('[^a-zäöüß0-9]+')) {
            if (String.isBlank(raw) || raw.length() < MIN_TOKEN_LENGTH || STOP_WORDS.contains(raw)) {
                continue;
            }
            tokens.add(raw);
            if (DE_TO_EN.containsKey(raw)) {
                tokens.add(DE_TO_EN.get(raw)); // German question, English corpus
            }
        }
        return tokens;
    }

    /** Title hits weigh more than body hits — a title match is a much stronger topic signal. */
    private static Integer scoreArticle(Knowledge__kav k, Set<String> tokens) {
        String title   = (k.Title   == null ? '' : k.Title.toLowerCase());
        String summary = (k.Summary == null ? '' : k.Summary.toLowerCase());
        Integer score = 0;
        for (String t : tokens) {
            if (title.contains(t))   score += 3;
            if (summary.contains(t)) score += 1;
        }
        return score;
    }

    private static Article toArticle(Knowledge__kav k, Integer score) {
        Article a = new Article();
        a.articleNumber = k.ArticleNumber;
        a.title         = k.Title;
        a.summary       = k.Summary;
        a.urlName       = k.UrlName;
        a.score         = score;
        a.citation      = 'HanseWatt Knowledge — ' + k.Title + ' (' + k.ArticleNumber + ')';
        return a;
    }
}