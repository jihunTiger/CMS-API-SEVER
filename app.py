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

app = FastAPI()


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
    cust_date: str = ""
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


class UpdatecustomerModel(BaseModel):
    cust_name: Optional[str]
    cust_email: Optional[EmailStr]
    cust_mobile: Optional[str]


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


@app.post("/customer/", response_description="Add new customer", response_model=customerModel, tags=["고객"])
async def create_customer(customer: customerModel = Body(...)):
    # 딕셔너리 자료형으로 변경
    customer = jsonable_encoder(customer)
    customer = {k: v for k, v in customer.items() if v != ''}

    new_customer = await db["customers"].insert_one(customer)
    created_customer = await db["customers"].find_one({"_id": new_customer.inserted_id})
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=created_customer)


@app.post("/customer/file", response_description="csv 파일 고객이 추가되었습니다.", tags=["고객"])
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
    "/customer/{id}", response_description="Update a customer", response_model=customerModel, tags=["고객"]
)
async def update_customer(id: str, customer: UpdatecustomerModel=Body(...)):
    customer={k: v for k, v in customer.dict().items() if v is not None}

    if len(customer) >= 1:
        update_result=await db["customers"].update_one({"_id": id}, {"$set": customer})

        if update_result.modified_count == 1:
            if (
                updated_customer := await db["customers"].find_one({"_id": id})
            ) is not None:
                return updated_customer

    if (existing_customer := await db["customers"].find_one({"_id": id})) is not None:
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
    "/touch/{id}",
     summary="터치히스토리 보기", response_model=List[touchModel], tags=["고객 터치"]
)
async def show_touchs(id: str, page: int = 1, per_page: int = 10):
    """
    id 필드에 고객아이디를 입력 :
    """
    cursor = db.touchs.find({"cust_id": PyObjectId(id)}).skip((page-1)*per_page).limit(per_page)
    touchs = await cursor.to_list(length=per_page)
    if len(touchs) >= 1:
        return touchs
    else:
        raise HTTPException(status_code=404, detail=f"{id} 고객의 history를 찾을수 없습니다.")

@app.post("/touch/{id}", description="", response_model=touchModel, tags=["고객 터치"])
async def add_touch(id: str, touch: touchModel = Body(...)):
    # 딕셔너리 자료형으로 변경
    touch = jsonable_encoder(touch)
    touch = {k: v for k, v in touch.items() if v != ''}

    touch["cust_id"] = PyObjectId(id)
    new_touch = await db.touchs.insert_one(touch)
    created_touch = await db["customers"].find_one({"_id": new_touch.inserted_id})
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=created_touch)