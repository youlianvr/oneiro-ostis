/*
 * This source file is part of Oneiro-OSTIS.
 * Distributed under the MIT License
 */

#pragma once

#include <sc-memory/sc_keynodes.hpp>

class OneiroKeynodes : public ScKeynodes
{
public:
  // Action classes
  static inline ScKeynode const action_record_attempt{"action_record_attempt", ScType::ConstNodeClass};
  static inline ScKeynode const action_retrieve_attempts{"action_retrieve_attempts", ScType::ConstNodeClass};

  // Classes of the experience ontology
  static inline ScKeynode const concept_experience_event{"concept_experience_event", ScType::ConstNodeClass};
  static inline ScKeynode const concept_attempt{"concept_attempt", ScType::ConstNodeClass};
  static inline ScKeynode const concept_outcome{"concept_outcome", ScType::ConstNodeClass};
  static inline ScKeynode const concept_subject{"concept_subject", ScType::ConstNodeClass};

  // Non-role relations
  static inline ScKeynode const nrel_outcome{"nrel_outcome", ScType::ConstNodeNonRole};
  static inline ScKeynode const nrel_subject{"nrel_subject", ScType::ConstNodeNonRole};
  static inline ScKeynode const nrel_action{"nrel_action", ScType::ConstNodeNonRole};
  static inline ScKeynode const nrel_object{"nrel_object", ScType::ConstNodeNonRole};
  static inline ScKeynode const nrel_timestamp{"nrel_timestamp", ScType::ConstNodeNonRole};
  static inline ScKeynode const nrel_prev_attempt{"nrel_prev_attempt", ScType::ConstNodeNonRole};

  // Result codes
  static inline ScKeynode const concept_success{"concept_success", ScType::ConstNodeClass};
  static inline ScKeynode const concept_failure{"concept_failure", ScType::ConstNodeClass};
};
