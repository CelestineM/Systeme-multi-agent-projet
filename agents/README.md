# Agents package

This folder contains the robot logic previously grouped in a single file.

## Structure

- `knowledge.py`: local map memory and merge logic.
- `navigation.py`: movement and exploration strategies (`Naive`, `A* + frontier`).
- `communication.py`: communication policies (`NoKnowledgeSharing`, `LocalKnowledgeSharing`, `SmartColorKnowledgeSharing`).
- `policy.py`: high-level decision making and behavior version selection.
- `robot.py`: base `Robot` class and concrete `green/yellow/red` agents.

## Smart communication rules

The smart sharing policy applies two rules:

1. **Share waste positions with matching color only**
   - yellow waste information is shared to yellow robots only,
   - red waste information is shared to red robots only,
   - green waste information is shared to green robots only.
2. **Share deposit updates immediately**
   - after a `deposit` action (including waste splitting), nearby robots receive updated local information.

Implementation note: smart sharing uses the `communication` package message primitives (`Message`, `MessagePerformative.INFORM_REF`, `MessageService`) so robots exchange filtered map updates through agent mailboxes before deliberation.

This reduces noise and helps each robot focus on relevant targets.
