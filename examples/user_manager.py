"""
User manager with bugs for testing Debug Agent
"""

users = [
    {"id": 1, "name": "Alice", "city": "Beijing"},
    {"id": 2, "name": "Bob", "city": "Shanghai"},
    {"id": 3, "name": "Charlie", "city": "Beijing"},
]

def get_user_by_id(user_id):
    """Get user by ID"""
    for user in users:
        if user["id"] == user_id:
            return user
    return None

def get_user_city(user_id):
    """Get user's city - BUG: returns wrong field"""
    user = get_user_by_id(user_id)
    if user:
        return user["name"]  # BUG: Should return city, not name
    return None

def get_users_in_city(city):
    """Get all users in a city"""
    result = []
    for user in users:
        # BUG: Should be user["city"] == city
        if user["name"] == city:
            result.append(user)
    return result

def add_user(name, city):
    """Add a new user"""
    new_id = max(u["id"] for u in users) + 1
    users.append({"id": new_id, "name": name, "city": city})
    return new_id

if __name__ == "__main__":
    print("User Manager Test:")
    print(f"User 1: {get_user_by_id(1)}")
    print(f"City of user 1: {get_user_city(1)}")  # Will print "Alice" instead of "Beijing"
    print(f"Users in Beijing: {get_users_in_city('Beijing')}")  # Will return empty list
