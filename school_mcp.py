
from mcp.server.fastmcp import FastMCP

import nest_asyncio


# Fix async loop issue in notebooks

nest_asyncio.apply()


# Create MCP Server

mcp = FastMCP("SchoolTools")


"""

FastMCP automatically:

Creates tool APIs

Registers functions

Handles communication

Sends metadata to AI models

Manages request/response flow

"""

# MCP Tool

@mcp.tool()

def get_student_marks(name: str) -> str:

    """

    Returns marks of a student

    """

    students = {

        "rahul": 88,

        "aman": 92,

        "neha": 95

    }

    marks = students.get(name.lower())

    if marks:

        return f"{name} scored {marks} marks"

    return "Student not found"

print("MCP Server Created Successfully")


get_student_marks("aman")
