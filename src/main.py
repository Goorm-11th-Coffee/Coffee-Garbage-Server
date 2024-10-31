from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, AwareDatetime
from sqlalchemy.orm import Session
from typing import List

from src.config import database
from src.model.user import User
from src.model.collect_rule import CollectRule
from src.model.collect_transaction import CollectTransaction
import httpx

app = FastAPI(version="1.0.0", docs_url="/api/swagger", redoc_url="/api/docs")


database.Base.metadata.create_all(bind=database.engine)


class UserRead(BaseModel):
    id: int
    token: str
    name: str
    address: str
    phone_number: str
    role: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class RuleRead(BaseModel):
    cafe_id: int
    weekday: int
    time: str

    class Config:
        orm_mode = True


class HistoryRead(BaseModel):
    id: int
    cafe_id: int
    client_name: str
    time: datetime
    amount: int

    class Config:
        orm_mode = True


@app.get("/api/login/kakao/oauth", response_model=List[UserRead])
async def login_kakao_oauth(code: str):
    # Kakao 토큰 요청 URL
    token_url = "https://kauth.kakao.com/oauth/token"

    # 토큰 요청 파라미터
    data = {
        "grant_type": "authorization_code",
        "client_id": "1153355",
        "redirect_uri": "https://kdbda913f9220a.user-app.krampoline.com/api/login/kakao/oauth",
        "code": code,
    }

    # 토큰 요청
    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, data=data)

    # 요청 성공 여부 확인
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Failed to obtain access token")

    # Access Token 정보 파싱
    token_data = response.json()
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": token_data.get("expires_in"),
        "scope": token_data.get("scope"),
        "token_type": token_data.get("token_type")
    }


@app.get("/api/users", response_model=List[UserRead])
def read_users(skip: int = 0, limit: int = 10, db: Session = Depends(database.get_db)):
    print("read_users_hi")
    users = db.query(User).offset(skip).limit(limit).all()
    return users


@app.get("/api/users/{user_id}", response_model=UserRead)
def read_user(user_id: int, db: Session = Depends(database.get_db)):
    print("read_user_hi")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


class CollectDays(BaseModel):
    weekday: int
    time: str


class CoffeeRequest(BaseModel):
    collect_days: List[CollectDays]
    amount: int
    position: str


class CoffeeHistory(BaseModel):
    history_id: int
    client_name: str
    time: AwareDatetime
    state: str
    amount: int


class CancelCoffee(BaseModel):
    history_id: int


@app.get("/health")
async def health_check():
    return {"message": "I'm healthy"}


@app.get("/api/coffee/{cafe_id}/rule", status_code=200, response_model=List[RuleRead])
async def get_coffee_rule(cafe_id: int, db: Session = Depends(database.get_db)) -> dict:
    rules = db.query(CollectRule).filter(CollectRule.cafe_id == cafe_id).all()
    if rules is None:
        raise HTTPException(status_code=404, detail="User not found")

    return rules


@app.post("/api/coffee/{cafe_id}/rule", status_code=201)
async def post_coffee_rule(cafe_id: int, coffee_request: CoffeeRequest, db: Session = Depends(database.get_db)) -> dict:
    # old_rules = db.query(CollectRule).filter(CollectRule.cafe_id == cafe_id).all()
    #
    # for old_rule in old_rules:
    #     db.delete(old_rule)

    cafe_id = coffee_request.cafe_id
    collect_days = coffee_request.collect_days

    for collect_day in collect_days:
        db.add(CollectRule(cafe_id=cafe_id, weekday=collect_day.weekday, time=collect_day.time))

    db.commit()

    return None


@app.get("/api/coffee/{cafe_id}/transaction", status_code=200, response_model=List[HistoryRead])
async def coffee_history(cafe_id: int, db: Session = Depends(database.get_db)) -> dict:
    histories = db.query(CollectTransaction).filter(CollectTransaction.cafe_id == cafe_id).all()

    return histories


@app.post("/api/coffee/{cafe_id}/transaction", status_code=201)
async def coffee_history(cafe_id: int, coffee_history: CoffeeHistory, db: Session = Depends(database.get_db)) -> dict:
    db.add(CollectTransaction(id=coffee_history.history_id, cafe_id=cafe_id, client_name=coffee_history.client_name,
                              time=coffee_history.time, amount=coffee_history.amount, status="Waiting"))

    db.commit()
    return None


@app.delete("/api/coffee/{cafe_id}/transaction", status_code=204)
async def coffee_cancel(cafe_id: int, cancel_coffee: CancelCoffee, db: Session = Depends(database.get_db)):
    histories = db.query(CollectTransaction).filter(CollectTransaction.cafe_id == cafe_id,
                                                    CollectTransaction.id == cancel_coffee.history_id).all()

    db.delete(histories)
    db.commit()

    return None


@app.get("/api/coffee/{cafe_id}/carbon", status_code=200)
async def carbon(cafe_id: int, db: Session = Depends(database.get_db)) -> dict:
    histories = db.query(CollectTransaction).filter(CollectTransaction.cafe_id == cafe_id
                                                    , CollectTransaction.status == "COMPLETED").all()

    amount = 0

    for history in histories:
        amount += history.amount

    return {"carbon": amount}
