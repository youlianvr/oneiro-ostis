/*
 * This source file is part of Oneiro-OSTIS.
 * Distributed under the MIT License
 */

#include "oneiroModule.hpp"

#include "agents/RecordAttemptAgent.hpp"
#include "agents/RetrieveAttemptsAgent.hpp"

SC_MODULE_REGISTER(OneiroModule)
    ->Agent<RecordAttemptAgent>()
    ->Agent<RetrieveAttemptsAgent>();
