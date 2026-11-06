"""Checks for unresolved_citations and the citations-not-on-pubmed task."""

from .checks import result
from .identity import input_problem, output_problem, same_references, subset_from_rows
from .rows import load_rows


def verify_input(value):
    problem = input_problem(value)
    if problem:
        return result(False, problem[1])
    return result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    problem = input_problem(input_value) or output_problem(output_value, input_value)
    if problem:
        return result(False, problem[1])
    kind, payload = load_rows(workspace, input_value.references)
    if kind != "ok":
        return result(False, payload)
    if not same_references(output_value.unresolved, subset_from_rows(input_value.references, payload)):
        return result(False, "output is not the unresolved subset in resolution.json")
    return result(True, "output matches the recorded rows")


def verify_task(arguments, output, reference, workspace):
    problem = input_problem(arguments) or output_problem(output, arguments)
    if problem:
        return result(False, problem[1])
    # A tool run never receives the pin. Judge that call from resolution.json.
    if reference is not None:
        problem = output_problem(reference, arguments)
        if problem:
            return result(False, problem[1])
        if not same_references(output.unresolved, reference.unresolved):
            return result(False, "output does not match the reference")
    kind, payload = load_rows(workspace, arguments.references)
    if kind != "ok":
        return result(False, payload)
    if not same_references(output.unresolved, subset_from_rows(arguments.references, payload)):
        return result(False, "resolution.json does not support the output")
    if reference is None:
        return result(True, "output matches the recorded rows")
    return result(True, "output matches the reference")
