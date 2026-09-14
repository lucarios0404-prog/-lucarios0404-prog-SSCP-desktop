import asyncio
from app.database import SessionLocal
from app.models.user import User
from app.core.security import get_password_hash

def create_admin():
    db = SessionLocal()
    
    # Check if admin already exists
    admin = db.query(User).filter(User.email == "admin@sscp.com").first()
    if admin:
        print("Admin user already exists!")
        return
        
    print("Creating admin user...")
    new_user = User(
        name="Administrador",
        email="admin@sscp.com",
        hashed_password=get_password_hash("password123"),
        role="admin"
    )
    
    db.add(new_user)
    db.commit()
    print("Admin user created successfully: admin@sscp.com / password123")
    
if __name__ == "__main__":
    create_admin()
