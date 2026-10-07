/* Distributed under the MIT License. */
#include "SaveMemoryAgent.hpp"
#include "../keynodes/OneiroKeynodes.hpp"

ScAddr SaveMemoryAgent::GetActionClass() const
{
  return OneiroKeynodes::action_oneiro_save_memory;
}

ScResult SaveMemoryAgent::DoProgram(ScAction & action)
{
  // The coordinator must quiesce writes before invoking this action. Save is
  // an explicit filesystem checkpoint, not an ACID/crash-atomic snapshot.
  // The action completion itself is generated after the saved state.
  if (!m_context.Save())
    return action.FinishUnsuccessfully();
  return action.FinishSuccessfully();
}
