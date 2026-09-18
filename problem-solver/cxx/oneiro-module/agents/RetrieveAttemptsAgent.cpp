/*
 * This source file is part of Oneiro-OSTIS.
 * Distributed under the MIT License
 */

#include "RetrieveAttemptsAgent.hpp"

#include <sc-agents-common/utils/IteratorUtils.hpp>

#include "../keynodes/OneiroKeynodes.hpp"

RetrieveAttemptsAgent::RetrieveAttemptsAgent()
{
  m_logger =
      utils::ScLogger(utils::ScLogger::ScLogType::File, "logs/RetrieveAttemptsAgent.log", utils::ScLogLevel::Info);
}

ScAddr RetrieveAttemptsAgent::GetActionClass() const
{
  return OneiroKeynodes::action_retrieve_attempts;
}

/*
 * Arguments:
 *   rrel_1: subject node  (required)
 *   rrel_2: action node   (optional filter)
 *
 * Result: a structure containing every attempt of the given subject
 * (optionally filtered by action), with its subject and outcome relations.
 */
ScResult RetrieveAttemptsAgent::DoProgram(ScAction & action)
{
  auto const & [subject, actFilter] = action.GetArguments<2>();

  if (!subject.IsValid())
  {
    m_logger.Error("RetrieveAttemptsAgent: subject argument is invalid.");
    return action.FinishWithError();
  }

  ScAddr const result = m_context.GenerateNode(ScType::ConstNode);

  ScIterator5Ptr it = m_context.CreateIterator5(
      ScType::Unknown,
      ScType::ConstCommonArc,
      subject,
      ScType::ConstPermPosArc,
      OneiroKeynodes::nrel_subject);

  while (it->Next())
  {
    ScAddr const attempt = it->Get(0);

    // optional action filter
    if (actFilter.IsValid())
    {
      bool actionMatches = false;
      ScIterator5Ptr actIt = m_context.CreateIterator5(
          attempt, ScType::ConstCommonArc, actFilter, ScType::ConstPermPosArc, OneiroKeynodes::nrel_action);
      if (actIt->Next())
        actionMatches = true;
      if (!actionMatches)
        continue;
    }

    m_context.GenerateConnector(ScType::ConstPermPosArc, result, attempt);
  }

  action.SetResult(result);
  return action.FinishSuccessfully();
}
