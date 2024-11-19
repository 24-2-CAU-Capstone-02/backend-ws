from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager
from typing import Dict, List
from dataclasses import dataclass
import json
import redis
import asyncio

app = FastAPI()
redis_client = redis.Redis(
    host="localhost", port=6379, db=0, decode_responses=True
)
pubsub = redis_client.pubsub()
pubsub_task = None
connected_clients = {}


async def pubsub_loop():
    # get_message로 polling
    while True:
        message = pubsub.get_message()
        if message != None:
            room_id = message.get("channel")
            message_data = json.loads(message["data"])

            if message_data.get("type") == "choice":
                for client in connected_clients.get(room_id, []):
                    data = json.loads(message_data.get("data"))
                    await client.send_json(data)
            if message_data.get("type") == "refresh":
                for client in connected_clients.get(room_id, []):
                    await client.send_json({"type": "refresh"})
        else:
            await asyncio.sleep(0.1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pubsub_task

    pubsub_task = asyncio.create_task(pubsub_loop())

    yield

    if pubsub_task:
        pubsub_task.cancel()
        try:
            await pubsub_task
        except asyncio.CancelledError:
            pass
    pubsub.close()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        if data.get("type") == "connect":
            room_id = data.get("roomId")

            session_token = data.get("sessionToken")
            member_id = await verify_user(room_id, session_token)

            if member_id != None:
                if room_id not in connected_clients:
                    connected_clients[room_id] = []
                    pubsub.subscribe(room_id)
                
                connected_clients[room_id].append(websocket)
                await websocket.send_json({"type": "connect", "status": "success"})

            else:
                await websocket.send_json({"type": "connect", "status": "fail"})
                await websocket.close()
                return

            while True:
                message = await websocket.receive_json()

                if message.get("type") == "choice":
                    menu_id = message.get("menuId")
                    quantity = message.get("quantity")

                    if menu_id == None or quantity == None:
                        continue

                    redis_client.hset(room_id, f"{menu_id}:{member_id}", quantity)
                    room_data = redis_client.hgetall(room_id)
                    response = {"type": "choice", "data": transform_dict(room_data)}

                    redis_client.publish(room_id, json.dumps(response))

                elif message.get("type") == "refresh":
                    response = {"type": "refresh"}
                    redis_client.publish(room_id, json.dumps(response))

    except WebSocketDisconnect:
        # 클라이언트가 연결을 끊었을 때 처리
        for room_id, clients in list(connected_clients.items()):
            if websocket in clients:
                clients.remove(websocket)
                if not clients:
                    del connected_clients[room_id]
                    pubsub.unsubscribe(room_id)
                break
    except Exception as e:
        # 그 이외 다른 모든 예외 상황
        print(f"Unhandled Exception : {e}")
        for room_id, clients in list(connected_clients.items()):
            if websocket in clients:
                clients.remove(websocket)
                if not clients:
                    del connected_clients[room_id]
                    pubsub.unsubscribe(room_id)
                break


async def verify_user(room_id: str, session_token: str) -> int:
    if room_id == None or session_token == None:
        return None
    
    return session_token  # 임시로 session_token을 member_id로 간주


def transform_dict(input_dict: dict):
    transformed_dict = {}
    
    for composite_key, quantity in input_dict.items():
        menu_id, member_id = composite_key.split(':')
        
        if menu_id not in transformed_dict:
            transformed_dict[menu_id] = {}

        transformed_dict[menu_id][member_id] = quantity
    
    return transformed_dict