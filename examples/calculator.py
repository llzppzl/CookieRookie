"""
Calculator with bugs for testing Debug Agent
"""

def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b

def divide(a, b):
    # BUG: Should check for zero division
    return a / b

def calculate(operation, a, b):
    if operation == "add":
        return add(a, b)
    elif operation == "subtract":
        return subtract(a, b)
    elif operation == "multiply":
        return multiply(a, b)
    elif operation == "divide":
        return divide(a, b)
    else:
        return None

if __name__ == "__main__":
    print("Calculator Test:")
    print(f"10 + 5 = {calculate('add', 10, 5)}")
    print(f"10 - 5 = {calculate('subtract', 10, 5)}")
    print(f"10 * 5 = {calculate('multiply', 10, 5)}")
    print(f"10 / 5 = {calculate('divide', 10, 5)}")
    
    # This will crash!
    print(f"10 / 0 = {calculate('divide', 10, 0)}")
