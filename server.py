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


# Function to check user validity by calling a backend API
async def verify_user(room_id: str, session_token: str) -> bool:
    # 예시: 실제 HTTP 호출로 room 및 token 검증
    return True  # 실제로는 백엔드 API를 호출해 응답 처리


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        if data["type"] == "connect":
            room_id = data["roomId"]
            session_token = data["sessionToken"]

            if await verify_user(room_id, session_token):
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

            if message["type"] == "choice":
                room_id = message["roomId"]
                menu_id = message["menuId"]
                member_id = message["memberId"]

                room_data = redis_client.get(room_id)
                if not room_data:
                    room_data = {}
                else:
                    room_data = json.loads(room_data)

                if menu_id not in room_data:
                    room_data[menu_id] = []
                if member_id not in room_data[menu_id]:
                    room_data[menu_id].append(member_id)

                redis_client.set(room_id, json.dumps(room_data))

                response = {"type": "choice", "roomId": room_data}

                for client in connected_clients.get(room_id, []):
                    await client.send_json(response)

            elif message["type"] == "refresh":
                response = {"type": "refresh"}
                for client in connected_clients.get(room_id, []):
                    await client.send_json(response)

    except WebSocketDisconnect:
        # 클라이언트가 연결을 끊었을 때 처리
        for clients in connected_clients.values():
            if websocket in clients:
                clients.remove(websocket)
