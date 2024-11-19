from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict, List
from dataclasses import dataclass
import json
import redis

app = FastAPI()
redis_client = redis.StrictRedis(
    host="localhost", port=6379, db=0, decode_responses=True
)
connected_clients = {}


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

                    for client in connected_clients.get(room_id, []):
                        await client.send_json(response)

                elif message.get("type") == "refresh":
                    response = {"type": "refresh"}
                    for client in connected_clients.get(room_id, []):
                        await client.send_json(response)

    except WebSocketDisconnect:
        # 클라이언트가 연결을 끊었을 때 처리
        for clients in connected_clients.values():
            if websocket in clients:
                clients.remove(websocket)


async def verify_user(room_id: str, session_token: str) -> int:
    if room_id == None or session_token == None:
        return None
    # 예시: 실제 HTTP 호출로 room 및 token 검증
    return 1  # 실제로는 백엔드 API를 호출해 응답 처리


def transform_dict(input_dict: dict):
    transformed_dict = {}
    
    for composite_key, quantity in input_dict.items():
        menu_id, member_id = composite_key.split(':')
        
        if menu_id not in transformed_dict:
            transformed_dict[menu_id] = {}

        transformed_dict[menu_id][member_id] = quantity
    
    return transformed_dict