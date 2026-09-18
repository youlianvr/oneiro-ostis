/*
 * This source file is part of Oneiro-OSTIS.
 * Distributed under the MIT License
 */

#include "RecordAttemptAgent.hpp"

#include <sc-agents-common/utils/IteratorUtils.hpp>

#include "../keynodes/OneiroKeynodes.hpp"

RecordAttemptAgent::RecordAttemptAgent()
{
  m_logger =
      utils::ScLogger(utils::ScLogger::ScLogType::File, "logs/RecordAttemptAgent.log", utils::ScLogLevel::Info);
}

ScAddr RecordAttemptAgent::GetActionClass() const
{
  return OneiroKeynodes::action_record_attempt;
}

/*
 * Arguments (attached to the action instance by rrel_1..rrel_5):
 *   rrel_1: subject node   (who performed the attempt)
 *   rrel_2: action node    (what was done)
 *   rrel_3: object node    (on what / where)
 *   rrel_4: outcome node   (concept_success / concept_failure / ...)
 *   rrel_5: optional ablation flag concept_no_temporal — skip chronology
 *
 * Effect:
 *   Generates a new attempt node of class concept_attempt; links subject,
 *   action, object and outcome to it via nrel_ relations (canonical binary
 *   relation pattern: main arc attempt->value with the relation arc as
 *   attribute); links the new attempt to the previous attempt of the same
 *   subject via nrel_prev_attempt (unless concept_no_temporal is passed);
 *   sets the attempt as the action result.
 */
ScResult RecordAttemptAgent::DoProgram(ScAction & action)
{
  auto const & [subject, act, object, outcome, noTemporalFlag] = action.GetArguments<5>();

  if (!subject.IsValid() || !act.IsValid() || !object.IsValid() || !outcome.IsValid())
  {
    m_logger.Error("RecordAttemptAgent: one or more arguments are invalid.");
    return action.FinishWithError();
  }

  bool const skipTemporal = noTemporalFlag.IsValid() && noTemporalFlag == OneiroKeynodes::concept_no_temporal;

  // Create the attempt node and put it into the attempt class.
  ScAddr const attempt = m_context.GenerateNode(ScType::ConstNode);
  m_context.GenerateConnector(ScType::ConstPermPosArc, OneiroKeynodes::concept_attempt, attempt);

  // Canonical binary-relation links from the attempt to its values.
  ScAddr const relations[] = {
      OneiroKeynodes::nrel_subject,
      OneiroKeynodes::nrel_action,
      OneiroKeynodes::nrel_object,
      OneiroKeynodes::nrel_outcome};
  ScAddr const values[] = {subject, act, object, outcome};

  for (size_t i = 0; i < 4; ++i)
  {
    ScAddr const mainArc = m_context.GenerateConnector(ScType::ConstCommonArc, attempt, values[i]);
    m_context.GenerateConnector(ScType::ConstPermPosArc, relations[i], mainArc);
  }

  // Chronological link: find the latest existing attempt of this subject
  // (one that has no nrel_prev_attempt successor yet) and link it.
  ScAddr latestAttempt;
  {
    ScIterator5Ptr it = m_context.CreateIterator5(
        ScType::Unknown,
        ScType::ConstCommonArc,
        subject,
        ScType::ConstPermPosArc,
        OneiroKeynodes::nrel_subject);
    while (it->Next())
    {
      ScAddr const candidate = it->Get(0);
      if (candidate == attempt)
        continue;
      // skip attempts that already have a successor
      ScIterator5Ptr succIt = m_context.CreateIterator5(
          ScType::Unknown,
          ScType::ConstCommonArc,
          candidate,
          ScType::ConstPermPosArc,
          OneiroKeynodes::nrel_prev_attempt);
      if (succIt->Next())
        continue;
      latestAttempt = candidate;
    }
  }

  if (latestAttempt.IsValid() && !skipTemporal)
  {
    // latestAttempt <-nrel_prev_attempt- arc -target- attempt
    ScAddr const mainArc = m_context.GenerateConnector(ScType::ConstCommonArc, attempt, latestAttempt);
    m_context.GenerateConnector(ScType::ConstPermPosArc, OneiroKeynodes::nrel_prev_attempt, mainArc);
  }

  m_logger.Info("RecordAttemptAgent: attempt recorded.");

  // Wrap the attempt into a result structure and hand it to the action.
  ScAddr const result = m_context.GenerateNode(ScType::ConstNode);
  m_context.GenerateConnector(ScType::ConstPermPosArc, result, attempt);
  action.SetResult(result);
  return action.FinishSuccessfully();
}
