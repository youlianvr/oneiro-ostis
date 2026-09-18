# Oneiro-OSTIS — черновик онтологии опыта

> Статус: draft для обсуждения. Ляжет в KB после подъёма стека (ступень 1).
> Здесь фиксируем концепты, роли и связи до того, как писать SCs-файлы и C++-агентов.

## 1. Суть

Опыт агента — это события, связанные с субъектом, временем и результатами.
Всё это нативно в sc-графе: узлы-события, роли (агент-субъект / среда / результат),
временные связи и оценки. Поверх этой структуры работает сон: реплей альтернативных
стратегий по записанному дереву решений.

## 2. Базовые концепты (nrel- и sc-отношения)

| Концепт | Тип | Назначение |
|---|---|---|
| `oneiro_experience_event` | sc_node_class | класс всех событий опыта |
| `oneiro_action_attempt` | sc_node_class | попытка действия в мире (атомарный эпизод) |
| `oneiro_decision_point` | sc_node_class | точка выбора, из которой исходят альтернативы |
| `oneiro_strategy` | sc_node_class | выбранная/предложенная стратегия действия |
| `oneiro_subject` | sc_node_class | сам агент (роль `rrel_oneiro_agent`) |
| `oneiro_world_state` | sc_node_class | наблюдаемое состояние среды до/после |

### Отношения

| Отношение | Тип | Связывает |
|---|---|---|
| `nrel_oneiro_participant` | nrel_role | событие ↔ субъект (кто совершал) |
| `nrel_oneiro_action` | nrel_role | событие ↔ действие (что делал) |
| `nrel_oneiro_object` | nrel_role | событие ↔ объект действия |
| `nrel_oneiro_result` | nrel_role | событие ↔ результат (успех/неудача/оценка) |
| `nrel_oneiro_next_state` | nrel_edge | состояние до → состояние после |
| `nrel_oneiro_prev_event` | nrel_edge | событие ↔ предыдущее событие (порядок опыта) |
| `nrel_oneiro_chosen_strategy` | nrel_edge | decision point ↔ фактическая стратегия |
| `nrel_oneiro_alt_strategy` | nrel_edge | decision point ↔ сгенерированная во сне альтернатива |
| `nrel_oneiro_replay_result` | nrel_edge | альтернатива ↔ вердикт точного реплея |
| `nrel_oneiro_timestamp` | nrel_edge | событие ↔ временнáя метка |

> Точные nrel-имена сверим с конвенциями существующих KB (ims.ostis.kb) перед написанием файлов —
> этот список не финальный, а рабочий словарь.

## 3. Шаблон одного эпизода (scg)

Тройка концептов в духе Шабалинского, применённая к одному событию:

```text
experience_event → next_state
        ↓
decision_point → chosen_strategy / alt_strategy (во сне)
```

Семантика: событие опыта переводит мир из состояния A в состояние B; если в этом
событии был выбор, точка решения связывает фактическую стратегию и, во сне,
альтернативные.

## 4. SCs-представление одного эпизода

```scs
event_1
<- oneiro_action_attempt;
<- oneiro_experience_event;
=> nrel_oneiro_participant:: [agent_self];;
=> nrel_oneiro_action:: [navigate_east];;
=> nrel_oneiro_object:: [room_3];;
=> nrel_oneiro_result:: [success];;
=> nrel_oneiro_next_state:: world_state_2;;
<= nrel_oneiro_prev_event:: event_0;;
```

Сноска на идентичность: без автоинкремента `event_1..N` становится лишним
и создаёт более высокого порядка идентичность — генератор UID для эпизодов будет
частью C++-агента записи опыта.

## 5. Что дальше

- Сверить имена отношений с `ims.ostis.kb` и `ostis-example-app/repo.path` (SCs-конвенции).
- Написать `kb/oneiro_ontology.scs` + `kb/episodes/*.scs` (генерация из лога среды).
- C++-агент: подписка на действие → запись эпизода по шаблону выше.
