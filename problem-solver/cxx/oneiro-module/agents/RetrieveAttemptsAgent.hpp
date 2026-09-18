/*
 * This source file is part of Oneiro-OSTIS.
 * Distributed under the MIT License
 */

#pragma once

#include <sc-memory/sc_agent.hpp>

class RetrieveAttemptsAgent : public ScActionInitiatedAgent
{
public:
  RetrieveAttemptsAgent();

  ScAddr GetActionClass() const override;

  ScResult DoProgram(ScAction & action) override;
};
