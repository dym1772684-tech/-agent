from fastapi import FastAPI,Path,Query,Depends,Request
from pydantic import BaseModel,Field
from fastapi.responses import HTMLResponse,FileResponse
from fastapi import HTTPException
import uvicorn
from sqlalchemy.ext.asyncio import create_async_engine
app=FastAPI(title="旅游agent")
class Struct(BaseModel):
    code:int
    message:str
    data:float
@app.middleware("http")
async def middleware1(request:Request,call_next):
    print(request.method)
    print(request.url)
    print(request.client)
    print(request.query_params)
    print(request.path_params)
    print(request.url.path)
    print(request.headers)
    print(request.url.hostname)
    print(request.url.scheme)
    print(request.url.query)
    await call_next(request)
@app.get("/get",response_model=HTMLResponse)
async def get():
    return HTMLResponse(content="<h1>hello world</h1>",status_code=200,media_type="text/html")
@app.get("/get/{id}",response_class=Struct)
async def get_id(iid:int=Path(...,title="id",description="id",ge=1,le=100)):
    return Struct(code=200,message="success",data=iid)
@app.get("/get2")
async def get2(name:str=Query(...,title="name",description="name",min_length=1,max_length=10)):
    return {"name":name}
if __name__=="__main__":
    uvicorn.run(app,host="0.0.0.0",port=8000)
