"""The deterministic verifier: each tool's checks live in its own module, on contract instances."""

from contract import Task, Tool

from . import pin, unresolved

TOOLS = {
    Tool.UNRESOLVED_CITATIONS: unresolved,
    Tool.PIN_UNRESOLVED: pin,
}
TASKS = {Task.CITATIONS_NOT_ON_PUBMED: unresolved.verify_task}


def verify_input(tool, value):
    return TOOLS[Tool(tool)].verify_input(value)


def verify_output(tool, input_value, output_value, workspace):
    return TOOLS[Tool(tool)].verify_output(input_value, output_value, workspace)


def verify_task(task, arguments, output, reference, workspace):
    return TASKS[Task(task)](arguments, output, reference, workspace)
