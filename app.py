from datetime import datetime
from functools import lru_cache
from fastapi import FastAPI, Body, HTTPException, status, File, UploadFile
from fastapi.responses import Response, JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, EmailStr
from bson import ObjectId
from typing import Optional, List, Union
import motor.motor_asyncio
import csv
import codecs
from config import Settings
from fastapi.openapi.utils import get_openapi

app = FastAPI()

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="샵이브이 고객관리 시스템 API",
        version="0.1.0",
        description="고객관리 시스템에 필요한 API 입니다. ",
        routes=app.routes,
    )
    openapi_schema["info"]["x-logo"] = {
        "url": "https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png"
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

@lru_cache()
def get_settings():
    return Settings()


client = motor.motor_asyncio.AsyncIOMotorClient(get_settings().MONGODB_URL)
db = client.test


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid objectid")
        return ObjectId(v)

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")


class MongoBaseModel(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")

    class Config:
        json_encoders = {ObjectId: str}
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        # orm_mode = True


class customerModel(MongoBaseModel):
    cust_name: str = Field(...)
    cust_mobile: str = ""
    cust_type: str = ""
    cust_email: str = ""
    cust_route: str = ""
    created_date: str = ""
    cust_purpose: str = ""
    cust_area: str = ""
    cust_status: str = ""
    cust_remark: str = ""

    class Config:
 
        schema_extra = {
            "example": {
                "cust_name": "박천수",
                "cust_mobile": "jdoe@example.com",
                "cust_type": "비회원",
                "기타": "...",
            }
        }


class UpdateCustomerModel(BaseModel):
    cust_name: Optional[str]
    cust_email: Optional[EmailStr]
    cust_mobile: Optional[str]
    modified_date : Optional[str]


class touchModel(MongoBaseModel):
    cust_id: Optional[PyObjectId]
    touch_date: str = ""
    touch_time: str = ""
    touch_desc: str = ""
    touch_partner: str = ""   #누가 발생시킨건지
    touch_chann: str = ""  # 열거형 
    touch_type: str = ""   # 열거형 사용으로 드롭다운 선택
    
    class Config:

        schema_extra = {
            "example": {
                "touch_date": "2023-10-10",
                "touch_time": "17:30", 
                "touch_desc": "터치한 내용을 입력",
                "touch_type": "inbound_call",
                "touch_chann": "call"
            }
        }

class UpdateTouchModel(BaseModel):
    touch_date: Union[str, None]
    touch_time: Union[str, None]
    touch_desc: Union[str, None]
    touch_partner: Union[str, None]   #누가 발생시킨건지
    touch_chann: Union[str, None]  # 열거형 
    touch_type: Union[str, None]   # 열거형 사용으로 드롭다운 선택

@app.post("/customer/", response_description="Add new customer", response_model=customerModel, tags=["고객"])
async def create_customer(customer: customerModel = Body(...)):
    # 딕셔너리 자료형으로 변경
    customer = jsonable_encoder(customer)
    customer = {k: v for k, v in customer.items() if v != ''}

    new_customer = await db["customers"].insert_one(customer)
    created_customer = await db["customers"].find_one({"_id": new_customer.inserted_id})
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=created_customer)


@app.post("/customer/file", summary="csv 파일을 이용하여 고객목록을 추가할 수 있습니다.", tags=["고객"])
async def create_customers(file: UploadFile = File(...)):
    # csvfile = open(file.fileName, 'r')
# import re
# p = re.compile(r'(0?10)[-]?(\d{4})[-]?(\d{4})')
 
# number = input()
 
# m = p.search(number)
 
# if m==None:
#     print("ERROR!")
# else:
#     if m.group(1)=='10':
#         print("0{}{}{}".format(m.group(1), m.group(2), m.group(3)))
#     else:
#         print("{}{}{}".format(m.group(1), m.group(2), m.group(3)))

    reader = csv.DictReader(codecs.iterdecode(file.file, 'utf-8'))

    for rows in reader:
        # customer: UpdatecustomerModel={k: v for k, v in rows.items() if v  != ''}

        customer: customerModel = {}
        touch_list: List = []

        for k, v in rows.items():

            if v != '':

                if k.startswith('cust_history'):
                    touch_list.append({"touch_desc" : v})
                else:
                    customer[k] = v

        await db["customers"].insert_one(customer)
        if len(touch_list) >= 1:
            for item in touch_list:
                touch: touchModel = item
                touch['cust_id'] = customer.get('_id')
                await db.touchs.insert_one(touch)
            

    file.file.close()
    return JSONResponse(status_code=status.HTTP_201_CREATED, content="고객이 생성되었습니다. ")
    


@app.get(
    "/customer/", response_description="List all customers", response_model=List[customerModel], tags=["고객"]
)
async def list_customers(page: int = 1, per_page: int = 10):
    cursor = db["customers"].find().skip((page-1)*per_page).limit(per_page)
    customers = await cursor.to_list(length=per_page)
    return customers


@app.get(
    "/customer/{id}",
     summary="고객 검색", response_model=customerModel, tags=["고객"]
)
async def show_customer(id: str):
    """
    id 필드에 고객 성명 이나 핸드폰번호 뒷 4자리를 넣으면 검색이 됩니다. :

    """
    customer = await db.customers.find_one({"$or": [{"cust_name": {"$regex": "^"+id}}, {"cust_mobile": {"$regex": id+"$"}}]})
    if customer is not None:
        return customer
    else:
        raise HTTPException(status_code=404, detail=f"{id} 고객을  찾을수 없습니다.")


@app.put(
    "/customer/{id}", summary="고객정보 업데이트", response_model=customerModel, tags=["고객"]
)
async def update_customer(id: str, customer: UpdateCustomerModel=Body(...)):
    customer={k: v for k, v in customer.dict().items() if v is not None}

    if len(customer) >= 1:
        customer['modifiled_date'] = datetime.datetime.now()
        update_result=await db["customers"].update_one({"_id": PyObjectId(id)}, {"$set": customer})

        if update_result.modified_count == 1:
            if (
                updated_customer := await db["customers"].find_one({"_id": PyObjectId(id)})
            ) is not None:
                return updated_customer

    if (existing_customer := await db["customers"].find_one({"_id": PyObjectId(id)})) is not None:
        return existing_customer

    raise HTTPException(status_code=404, detail=f"customer {id} not found")


@ app.delete(
    "/customer/{id}", response_description="Delete a customer", tags=["고객"]
)
async def delete_customer(id: str):
    delete_result=await db["customers"].delete_one({"_id": id})

    if delete_result.deleted_count == 1:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    raise HTTPException(status_code=404, detail=f"customer {id} not found")


@app.get(
    "/touch/{cust_id}",
     summary="터치히스토리 보기", response_model=List[touchModel], tags=["고객 터치"]
)
async def show_touchs(cust_id: str, page: int = 1, per_page: int = 10):
    """
    id 필드에 고객아이디를 입력 :
    """
    cursor = db.touchs.find({"cust_id": PyObjectId(cust_id)}).skip((page-1)*per_page).limit(per_page)
    touchs = await cursor.to_list(length=per_page)
    if len(touchs) >= 1:
        return touchs
    else:
        raise HTTPException(status_code=404, detail=f"{cust_id} 고객의 history를 찾을수 없습니다.")

@app.post("/touch/{cust_id}", summary="터치내용 저장", response_model=touchModel, tags=["고객 터치"])
async def add_touch(cust_id: str, touch: touchModel = Body(...)):
    """
    id 필드 : 고객의 유니크 id (고객 조회를 통해 획득)
    """
    touch = jsonable_encoder(touch)
    touch = {k: v for k, v in touch.items() if v != ''}

    touch["cust_id"] = PyObjectId(cust_id)
    new_touch = await db.touchs.insert_one(touch)
    created_touch = await db["customers"].find_one({"_id": new_touch.inserted_id})
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=created_touch)

@app.put(
    "/touch/{id}", summary="터치정보 업데이트", response_model=touchModel, tags=["고객 터치"]
)
async def update_touch(id: str, touch: UpdateTouchModel=Body(...)):
    """
    id 필드는 개별 터치정보의 uid  : 터치정보 수정 
    """
    touch={k: v for k, v in touch.dict().items() if v is not None}

    if len(touch) >= 1:
        update_result=await db.touchs.update_one({"_id": PyObjectId(id)}, {"$set": touch})

        if update_result.modified_count == 1:
            if (
                updated_touch := await db.touchs.find_one({"_id": PyObjectId(id)})
            ) is not None:
                return updated_touch

    if (existing_customer := await db.touchs.find_one({"_id": PyObjectId(id)})) is not None:
        return existing_customer

    raise HTTPException(status_code=404, detail=f" {id} 터치정보가 없습니다. ")