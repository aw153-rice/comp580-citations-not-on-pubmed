"""Checks for pin_unresolved. The pin writes no file; the task compares it as the answer key."""

from .checks import result
from .identity import input_problem, output_problem


def verify_input(value):
    problem = input_problem(value)
    if problem:
        return result(False, problem[1])
    return result(True, "input is valid")


def verify_output(input_value, output_value, _workspace):
    problem = input_problem(input_value) or output_problem(output_value, input_value)
    if problem:
        return result(False, problem[1])
    return result(True, "pin output is well formed")
