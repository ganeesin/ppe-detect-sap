import io
import os
import json
import traceback
import urllib.parse
import boto3
import copy
import botocore.response as br
import pyodata
import requests
from PIL import Image
import base64
from datetime import datetime, tzinfo,timezone,timedelta

from boto3.dynamodb.conditions import Key
from boto3.dynamodb.conditions import Attr

#clients
s3       = boto3.client('s3')
smclient = boto3.client('secretsmanager')
lookoutvision_client = boto3.client('lookoutvision')
ddb = boto3.resource('dynamodb')

sapauth={}

#constants
INCIDENT_SERVICE='/359600betrial/API_EHS_REPORT_INCIDENT_SRV'

def handler(event,context):
# Incoming image
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'],\
         encoding='utf-8')
    
    try:
    # Read the image object    
        response = s3.get_object(Bucket=bucket, Key=key)
        imgcopy  =  s3.get_object(Bucket=bucket, Key=key)

        imgbinary = imgcopy['Body'].read()        
        file_stream  = response['Body']

        image = Image.open(file_stream)
        image_type=Image.MIME[image.format]
        print(image_type)

        image_bytes = io.BytesIO()
        image.save(image_bytes, format=image.format)
        image_bytes = image_bytes.getvalue()
        detectIncident(image_bytes, image_type, key, imgbinary)

    except Exception as e:
        traceback.print_exc()
        return e
        
def detectIncident(image_bytes, image_type,key,imgbin):
        # Amazon Rekognition client
    rekognition = boto3.client('rekognition')
    response = rekognition.detect_protective_equipment(
        Image={'Bytes': image_bytes},
        SummarizationAttributes={
            'MinConfidence': 90,
            'RequiredEquipmentTypes': [
                'FACE_COVER',
                'HEAD_COVER',
                'HAND_COVER'
            ]
        }
    )
    
        
        
    print(key)
    result = len(response['Summary']['PersonsWithoutRequiredEquipment'])
    print('is Safety observation:'+str(result))
    
    if result > 0:
         #createNotification(image_bytes,image_type,key)
         createIncident(image_bytes,image_type,key,imgbin)
         
def createIncident(image, image_type, key,imgbin):
    IncidentNotification =  getODataClient(INCIDENT_SERVICE)
    #equipment,plant,material,object = key.split('/')
    # if you have any location or other attributed to map, this is optional   
    # ddbConfigTable = ddb.Table(os.environ.get('DDB_CONFIG_TABLE'))

   # response = ddbConfigTable.query(
     #   KeyConditionExpression=Key('notiftype').eq('06') & Key('equipment').eq(equipment),
      #  FilterExpression=Attr('plant').eq(plant) & Attr('material').eq(material)
    #)

    #configItem = response['Items']
    
    incidendate = datetime.utcnow().isoformat()[:-7]+'Z'
    print("date is"+incidendate)
    payload = {
        
    }
    #payload["IncidentUTCDateTime"] = datetime.utcnow().isoformat()[:-7]+'Z'
    payload["IncidentCategory"] = "003"
    payload["IncidentTitle"] = "Hello, From Pyodata"
    payload["IncidentUTCDateTime"]=incidendate
    print(payload["IncidentUTCDateTime"])
    create_request = IncidentNotification.entity_sets.A_Incident.create_entity()
    create_request.set(**payload)
    Incident = create_request.execute()

    print('SAP Incident number:'+Incident.IncidentUUID)
    

    attachResponse = createAttachment(key,Incident.IncidentUUID,image_type,imgbin)
    
def createAttachment(object,id,image_type,imgbin):
    # Create Attachment
    attachmentClient = _getattachmentClient(INCIDENT_SERVICE,
    slug=object,
    Incidentid=id,
    type=image_type)

    attachmentEntity = attachmentClient['uri']+"/A_Incident(guid" + "\'"+ str(id) + "\'"+ ")/to_Attachments"
    resp = attachmentClient['session'].post(attachmentEntity,data=imgbin)
    print(attachmentEntity)
    print(resp.text)
    return(resp.text)
    
def _getattachmentClient(service,**kwargs):

    sap_host = os.environ.get('SAP_HOST_NAME')
    sap_port = os.environ.get('SAP_PORT')
    sap_proto = os.environ.get('SAP_PROTOCOL')
    
    serviceuri = sap_proto + '://' + sap_host + ':' + sap_port + service
    
    
    authresponse = smclient.get_secret_value(
            SecretId=os.environ.get('SAP_AUTH_SECRET')
        )

    sapauth = json.loads(authresponse['SecretString'])
    session = requests.Session()
    session.headers.update({'APIKey': sapauth['APIKey']})
    response = session.head(serviceuri, headers={'x-csrf-token': 'fetch'})
    token = response.headers.get('x-csrf-token', '')
    session.headers.update({'x-csrf-token': token})
    
   
    session.headers.update({'Content-Type': kwargs.get('type')})
    session.headers.update({'Slug': kwargs.get('slug')})

    return{ 'session': session, 'uri': serviceuri }
    
def getODataClient(service,**kwargs):
    try:
        sap_host = os.environ.get('SAP_HOST_NAME')
        sap_port = os.environ.get('SAP_PORT')
        sap_proto = os.environ.get('SAP_PROTOCOL')
        serviceuri = sap_proto + '://' + sap_host + ':' + sap_port + service
       
        print('service call:'+serviceuri)
       #Secret Manager
        authresponse = smclient.get_secret_value(
            SecretId=os.environ.get('SAP_AUTH_SECRET')
        )

        sapauth = json.loads(authresponse['SecretString'])
        
       #Set session headers - Auth,token etc
        session = requests.Session()
        #session.auth = (sapauth['user'],sapauth['password'])
        session.headers.update({'APIKey': sapauth['APIKey']})
        response = session.head(serviceuri, headers={'x-csrf-token': 'fetch'})
        token = response.headers.get('x-csrf-token', '')
        print(token)
        session.headers.update({'x-csrf-token': token})

        oDataClient = pyodata.Client(serviceuri, session)
        
        return oDataClient

    except Exception as e:
          traceback.print_exc()
          return e



   




