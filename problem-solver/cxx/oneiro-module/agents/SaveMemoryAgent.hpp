/* Distributed under the MIT License. */
#pragma once

#include <sc-memory/sc_agent.hpp>

class SaveMemoryAgent : public ScActionInitiatedAgent
{
public:
  ScAddr GetActionClass() const override;
  ScResult DoProgram(ScAction & action) override;
};
