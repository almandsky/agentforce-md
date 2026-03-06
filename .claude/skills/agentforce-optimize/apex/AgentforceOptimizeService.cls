/**
 * @description STDM query service for the agentforce-optimize Claude Code skill.
 *              Queries the Session Trace Data Model (STDM) in Data Cloud to retrieve
 *              session traces, conversation turns, messages, and steps for issue analysis.
 *
 *              Deployed once per org by the agentforce-optimize skill (Phase 1 setup).
 *              All public methods accept dataSpaceName so no Data Space is hardcoded.
 *
 * Methods:
 *   findSessions(dataSpaceName, startIso, endIso, maxRows)        → JSON List<SessionSummary>
 *   getConversationDetails(dataSpaceName, sessionId)              → JSON ConversationData
 *   getMultipleConversationDetails(dataSpaceName, sessionIds)     → JSON List<ConversationData>
 */
public with sharing class AgentforceOptimizeService {

    // =========================================================================
    // Output wrappers
    // =========================================================================

    /** Lightweight session record returned by findSessions(). */
    public class SessionSummary {
        public String  session_id;
        public String  start_time;
        public String  end_time;
        public String  channel;
        public Long    duration_ms;
    }

    /** A single user/agent message within a turn. */
    public class MessageData {
        public String message_id;
        /** 'Input' (user) or 'Output' (agent) — raw STDM value */
        public String message_type;
        public String text;
        public String sent_at;
    }

    /**
     * A single internal step within a turn.
     * All issue-detection fields are included:
     *   - error      → non-null means ACTION_STEP failure (P1)
     *   - pre_vars / post_vars → null delta means variable not captured (P2)
     *   - duration_ms > 10 000 → slow action (P3)
     */
    public class StepData {
        public String step_id;
        /** TOPIC_STEP | LLM_STEP | ACTION_STEP | SESSION_END */
        public String step_type;
        public String name;
        public String start_time;
        public String end_time;
        public Long   duration_ms;
        /** Raw JSON input to the action (null when not an ACTION_STEP) */
        public String input;
        /** Raw JSON output from the action (null when not an ACTION_STEP) */
        public String output;
        /** Non-null indicates the action threw an error */
        public String error;
        /** Variable snapshot before this step (null when NOT_SET) */
        public String pre_vars;
        /** Variable snapshot after this step (null when NOT_SET) */
        public String post_vars;
    }

    /**
     * One conversational turn (AiAgentInteraction of type TURN).
     * Contains all messages and steps for that turn.
     */
    public class TurnData {
        public String interaction_id;
        /** Topic API name — null/mismatch signals a misroute (P1) */
        public String topic;
        public String start_time;
        public String end_time;
        public Long   duration_ms;
        public List<MessageData> messages;
        public List<StepData>    steps;

        public TurnData() {
            messages = new List<MessageData>();
            steps    = new List<StepData>();
        }
    }

    /**
     * Full conversation for one session: session header + ordered turns.
     * turn_count and action_error_count are pre-computed for quick triage.
     */
    public class ConversationData {
        public String  session_id;
        public String  start_time;
        public String  end_time;
        public String  channel;
        public Long    duration_ms;
        public Integer turn_count        = 0;
        public Integer action_error_count = 0;
        public List<TurnData> turns;

        public ConversationData() {
            turns = new List<TurnData>();
        }
    }

    // =========================================================================
    // Public API
    // =========================================================================

    /**
     * Find recent sessions within a date range, optionally filtered to a specific agent.
     *
     * Agent filtering uses the AiAgentSessionParticipant DMO:
     *   GenAiPlannerDefinition (MasterLabel = agentApiName)
     *     → ssot__AiAgentSessionParticipant__dlm (ssot__ParticipantId__c)
     *     → ssot__AiAgentSession__dlm (ssot__Id__c IN session list)
     *
     * @param dataSpaceName  Data Cloud Data Space API name (discovered in Phase 0)
     * @param startIso       ISO 8601 UTC start, e.g. '2025-03-01T00:00:00.000Z'
     * @param endIso         ISO 8601 UTC end
     * @param maxRows        Maximum sessions to return (e.g. 20)
     * @param agentApiName   MasterLabel of the Agentforce agent to filter by (null = all agents)
     * @return JSON-serialized List<SessionSummary>
     */
    public static String findSessions(String dataSpaceName, String startIso, String endIso, Integer maxRows, String agentApiName) {
        String sessionFilter = '';
        if (String.isNotBlank(agentApiName)) {
            List<String> plannerIds = resolvePlannerIds(agentApiName);
            if (!plannerIds.isEmpty()) {
                // Find all session IDs where one of the agent's planner versions was a participant
                String pInClause = '(\'' + String.join(plannerIds, '\',\'') + '\')';
                String partSql = 'SELECT ssot__AiAgentSessionId__c '
                               + 'FROM "ssot__AiAgentSessionParticipant__dlm" '
                               + 'WHERE ssot__ParticipantId__c IN ' + pInClause;
                ConnectApi.CdpQueryOutputV2 partResult = runQuery(partSql, dataSpaceName);
                if (partResult != null && partResult.data != null && !partResult.data.isEmpty()) {
                    List<String> sessionIds = new List<String>();
                    for (ConnectApi.CdpQueryV2Row row : partResult.data) {
                        String sid = col(row.rowData, 0);
                        if (sid != null) sessionIds.add(sid);
                    }
                    if (!sessionIds.isEmpty()) {
                        sessionFilter = '  AND ssot__Id__c IN (\'' + String.join(sessionIds, '\',\'') + '\') ';
                        System.debug(LoggingLevel.DEBUG, 'Agent filter: ' + plannerIds.size() + ' planner(s), '
                            + sessionIds.size() + ' session(s) for agent: ' + agentApiName);
                    }
                } else {
                    System.debug(LoggingLevel.WARN, 'No participant sessions found for agent: ' + agentApiName);
                }
            } else {
                System.debug(LoggingLevel.WARN, 'Agent not found: ' + agentApiName + ' — returning sessions for all agents');
            }
        }

        String sql =
              'SELECT ssot__Id__c, ssot__StartTimestamp__c, ssot__EndTimestamp__c, ssot__AiAgentChannelType__c '
            + 'FROM "ssot__AiAgentSession__dlm" '
            + 'WHERE ssot__StartTimestamp__c >= \'' + startIso + '\' '
            + '  AND ssot__StartTimestamp__c <= \'' + endIso   + '\' '
            + sessionFilter
            + 'ORDER BY ssot__StartTimestamp__c DESC '
            + 'LIMIT ' + maxRows;

        ConnectApi.CdpQueryOutputV2 result = runQuery(sql, dataSpaceName);
        List<SessionSummary> sessions = new List<SessionSummary>();

        if (result != null && result.data != null) {
            for (ConnectApi.CdpQueryV2Row row : result.data) {
                SessionSummary s = new SessionSummary();
                s.session_id  = col(row.rowData, 0);
                s.start_time  = col(row.rowData, 1);
                s.end_time    = col(row.rowData, 2);
                s.channel     = col(row.rowData, 3);
                s.duration_ms = durationMs(s.start_time, s.end_time);
                sessions.add(s);
            }
        }
        return JSON.serialize(sessions);
    }

    /**
     * Overload that queries sessions for all agents (no agent filter).
     * Kept for backwards compatibility; prefer the 5-argument version.
     */
    public static String findSessions(String dataSpaceName, String startIso, String endIso, Integer maxRows) {
        return findSessions(dataSpaceName, startIso, endIso, maxRows, null);
    }

    /**
     * Retrieve full conversation details for a single session.
     * Fetches interactions, messages, and steps (with error/variable fields).
     *
     * @param dataSpaceName  Data Cloud Data Space API name
     * @param sessionId      ssot__Id__c of the AiAgentSession
     * @return JSON-serialized ConversationData
     */
    public static String getConversationDetails(String dataSpaceName, String sessionId) {
        if (String.isBlank(sessionId)) return null;

        ConversationData convo = new ConversationData();
        convo.session_id = sessionId;

        // --- Session header ---
        String sessionSql =
              'SELECT ssot__StartTimestamp__c, ssot__EndTimestamp__c, ssot__AiAgentChannelType__c '
            + 'FROM "ssot__AiAgentSession__dlm" '
            + 'WHERE ssot__Id__c = \'' + String.escapeSingleQuotes(sessionId) + '\'';

        ConnectApi.CdpQueryOutputV2 sessionResult = runQuery(sessionSql, dataSpaceName);
        if (sessionResult != null && sessionResult.data != null && !sessionResult.data.isEmpty()) {
            List<Object> r = sessionResult.data[0].rowData;
            convo.start_time  = col(r, 0);
            convo.end_time    = col(r, 1);
            convo.channel     = col(r, 2);
            convo.duration_ms = durationMs(convo.start_time, convo.end_time);
        }

        // --- Interactions (turns) ---
        // ssot__TopicApiName__c included for misroute detection
        String interSql =
              'SELECT ssot__Id__c, ssot__TopicApiName__c, ssot__AiAgentInteractionType__c, '
            + '       ssot__StartTimestamp__c, ssot__EndTimestamp__c '
            + 'FROM "ssot__AiAgentInteraction__dlm" '
            + 'WHERE ssot__AiAgentSessionId__c = \'' + String.escapeSingleQuotes(sessionId) + '\' '
            + 'ORDER BY ssot__StartTimestamp__c';

        ConnectApi.CdpQueryOutputV2 interResult = runQuery(interSql, dataSpaceName);
        if (interResult == null || interResult.data == null || interResult.data.isEmpty()) {
            return JSON.serialize(convo);
        }

        Map<String, TurnData> turnById = new Map<String, TurnData>();
        List<String> turnIds = new List<String>();

        for (ConnectApi.CdpQueryV2Row row : interResult.data) {
            String interType = col(row.rowData, 2);
            // SESSION_END is a meta interaction, not a user turn
            if ('SESSION_END'.equalsIgnoreCase(interType)) continue;

            TurnData t         = new TurnData();
            t.interaction_id   = col(row.rowData, 0);
            t.topic            = col(row.rowData, 1);
            t.start_time       = col(row.rowData, 3);
            t.end_time         = col(row.rowData, 4);
            t.duration_ms      = durationMs(t.start_time, t.end_time);
            turnById.put(t.interaction_id, t);
            turnIds.add(t.interaction_id);
            convo.turns.add(t);
        }
        convo.turn_count = convo.turns.size();

        if (turnIds.isEmpty()) return JSON.serialize(convo);

        String inClause = '(\'' + String.join(turnIds, '\',\'') + '\')';

        // --- Messages ---
        String msgSql =
              'SELECT ssot__Id__c, ssot__AiAgentInteractionId__c, '
            + '       ssot__AiAgentInteractionMessageType__c, ssot__ContentText__c, '
            + '       ssot__MessageSentTimestamp__c '
            + 'FROM "ssot__AiAgentInteractionMessage__dlm" '
            + 'WHERE ssot__AiAgentInteractionId__c IN ' + inClause + ' '
            + 'ORDER BY ssot__MessageSentTimestamp__c';

        ConnectApi.CdpQueryOutputV2 msgResult = runQuery(msgSql, dataSpaceName);
        if (msgResult != null && msgResult.data != null) {
            for (ConnectApi.CdpQueryV2Row row : msgResult.data) {
                TurnData t = turnById.get(col(row.rowData, 1));
                if (t == null) continue;

                MessageData m  = new MessageData();
                m.message_id   = col(row.rowData, 0);
                m.message_type = col(row.rowData, 2); // 'Input' or 'Output'
                m.text         = col(row.rowData, 3);
                m.sent_at      = col(row.rowData, 4);
                t.messages.add(m);
            }
        }

        // --- Steps ---
        // All issue-detection fields are selected:
        //   ssot__ErrorMessageText__c        → Action error (P1)
        //   ssot__InputValueText__c          → Wrong action input (P2)
        //   ssot__OutputValueText__c         → Action output
        //   ssot__PreStepVariableText__c     → Pre-step variable snapshot (P2)
        //   ssot__PostStepVariableText__c    → Post-step variable snapshot (P2)
        //   ssot__EndTimestamp__c            → Step duration for slow action (P3)
        String stepSql =
              'SELECT ssot__Id__c, ssot__AiAgentInteractionId__c, '
            + '       ssot__AiAgentInteractionStepType__c, ssot__Name__c, '
            + '       ssot__StartTimestamp__c, ssot__EndTimestamp__c, '
            + '       ssot__InputValueText__c, ssot__OutputValueText__c, '
            + '       ssot__ErrorMessageText__c, '
            + '       ssot__PreStepVariableText__c, ssot__PostStepVariableText__c '
            + 'FROM "ssot__AiAgentInteractionStep__dlm" '
            + 'WHERE ssot__AiAgentInteractionId__c IN ' + inClause + ' '
            + 'ORDER BY ssot__StartTimestamp__c';

        ConnectApi.CdpQueryOutputV2 stepResult = runQuery(stepSql, dataSpaceName);
        if (stepResult != null && stepResult.data != null) {
            for (ConnectApi.CdpQueryV2Row row : stepResult.data) {
                TurnData t = turnById.get(col(row.rowData, 1));
                if (t == null) continue;

                StepData s   = new StepData();
                s.step_id    = col(row.rowData, 0);
                s.step_type  = col(row.rowData, 2);
                s.name       = col(row.rowData, 3);
                s.start_time = col(row.rowData, 4);
                s.end_time   = col(row.rowData, 5);
                s.duration_ms = durationMs(s.start_time, s.end_time);
                s.input      = notSet(col(row.rowData, 6));
                s.output     = notSet(col(row.rowData, 7));
                s.error      = notSet(col(row.rowData, 8));
                s.pre_vars   = notSet(col(row.rowData, 9));
                s.post_vars  = notSet(col(row.rowData, 10));

                if (s.error != null && 'ACTION_STEP'.equalsIgnoreCase(s.step_type)) convo.action_error_count++;
                t.steps.add(s);
            }
        }

        return JSON.serialize(convo);
    }

    /**
     * Retrieve full conversation details for multiple sessions.
     *
     * @param dataSpaceName  Data Cloud Data Space API name
     * @param sessionIds     List of ssot__Id__c values (keep under 20 to avoid CPU limits)
     * @return JSON-serialized List<ConversationData>
     */
    public static String getMultipleConversationDetails(String dataSpaceName, List<String> sessionIds) {
        List<ConversationData> results = new List<ConversationData>();
        if (sessionIds == null || sessionIds.isEmpty()) return JSON.serialize(results);

        for (String sid : sessionIds) {
            String detail = getConversationDetails(dataSpaceName, sid);
            if (String.isNotBlank(detail)) {
                ConversationData convo = (ConversationData) JSON.deserialize(detail, ConversationData.class);
                results.add(convo);
            }
        }
        return JSON.serialize(results);
    }

    // =========================================================================
    // Private helpers
    // =========================================================================

    /**
     * Resolve an Agentforce agent name to its GenAiPlannerDefinition IDs.
     *
     * Each deployed agent version creates a GenAiPlannerDefinition whose MasterLabel
     * matches the agent's display name (e.g. 'TeslaSupportAgent'). Returning all
     * matching versions ensures historical sessions from older deployments are included.
     *
     * Agent sessions are linked via ssot__AiAgentSessionParticipant__dlm where
     * ssot__ParticipantId__c holds the GenAiPlannerDefinition Id (16j... key prefix).
     *
     * @param agentApiName  MasterLabel of the agent (same as the agent's display name)
     * @return List of GenAiPlannerDefinition Ids; empty if not found
     */
    private static List<String> resolvePlannerIds(String agentApiName) {
        List<String> ids = new List<String>();
        try {
            List<GenAiPlannerDefinition> planners = [
                SELECT Id FROM GenAiPlannerDefinition
                WHERE MasterLabel = :agentApiName
            ];
            for (GenAiPlannerDefinition p : planners) {
                String id18 = String.valueOf(p.Id);
                ids.add(id18);
                // STDM DMO stores IDs inconsistently (15-char or 18-char) — include both
                if (id18.length() == 18) ids.add(id18.substring(0, 15));
            }
            if (ids.isEmpty()) {
                System.debug(LoggingLevel.WARN, 'No GenAiPlannerDefinition found for MasterLabel: ' + agentApiName);
            } else {
                System.debug(LoggingLevel.DEBUG, 'Resolved ' + ids.size() + ' planner version(s) for agent "' + agentApiName + '": ' + ids);
            }
        } catch (Exception e) {
            System.debug(LoggingLevel.WARN, 'resolvePlannerIds failed for "' + agentApiName + '": ' + e.getMessage());
        }
        return ids;
    }

    private static ConnectApi.CdpQueryOutputV2 runQuery(String sql, String dataSpaceName) {
        System.debug(LoggingLevel.DEBUG, 'AgentforceOptimize CDP query (' + dataSpaceName + '): ' + sql);
        ConnectApi.CdpQueryInput inp = new ConnectApi.CdpQueryInput();
        inp.sql = sql;
        try {
            ConnectApi.CdpQueryOutputV2 result = ConnectApi.CdpQuery.queryAnsiSqlV2(inp, dataSpaceName);
            Integer rowCount = (result != null && result.data != null) ? result.data.size() : 0;
            System.debug(LoggingLevel.DEBUG, 'Rows returned: ' + rowCount);
            return result;
        } catch (Exception e) {
            System.debug(LoggingLevel.ERROR,
                'CDP query failed [' + dataSpaceName + ']: ' + e.getMessage() + ' | SQL: ' + sql);
            return null;
        }
    }

    /** Safely extract a column value as String; returns null for empty/null cells. */
    private static String col(List<Object> row, Integer i) {
        if (row == null || i >= row.size() || row[i] == null) return null;
        return String.valueOf(row[i]);
    }

    /** Return null when the value is the STDM "NOT_SET" sentinel or blank. */
    private static String notSet(String val) {
        if (String.isBlank(val) || val == 'NOT_SET') return null;
        return val;
    }

    /** Compute millisecond duration between two ISO timestamp strings; null on any failure. */
    private static Long durationMs(String startTs, String endTs) {
        if (String.isBlank(startTs) || String.isBlank(endTs)) return null;
        try {
            Datetime startDt = parseTs(startTs);
            Datetime endDt   = parseTs(endTs);
            if (startDt == null || endDt == null) return null;
            return endDt.getTime() - startDt.getTime();
        } catch (Exception e) {
            return null;
        }
    }

    /** Parse an ISO 8601 timestamp string into a Datetime, with fallback strategies. */
    private static Datetime parseTs(String ts) {
        if (String.isBlank(ts)) return null;
        // Strategy 1: ISO 8601 via JSON deserialise
        try {
            return (Datetime) JSON.deserialize('"' + ts + '"', Datetime.class);
        } catch (Exception e1) {
            System.debug(LoggingLevel.FINE, 'parseTs strategy 1 failed for "' + ts + '": ' + e1.getMessage());
        }
        // Strategy 2: Datetime.valueOf (handles 'yyyy-MM-dd HH:mm:ss' format)
        try {
            return Datetime.valueOf(ts);
        } catch (Exception e2) {
            System.debug(LoggingLevel.FINE, 'parseTs strategy 2 failed for "' + ts + '": ' + e2.getMessage());
        }
        // Strategy 3: epoch milliseconds
        try {
            return Datetime.newInstance(Long.valueOf(ts));
        } catch (Exception e3) {
            System.debug(LoggingLevel.FINE, 'parseTs strategy 3 failed for "' + ts + '": ' + e3.getMessage());
        }
        return null;
    }
}
