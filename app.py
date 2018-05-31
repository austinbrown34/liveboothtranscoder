from flask import Flask, jsonify, make_response, request, abort, Response
import subprocess
import os
import boto3
import botocore
import uuid
import requests
from flask_mail import Mail, Message
import json
from zappa.async import task
# import sendgrid
# from sendgrid.helpers.mail import *
import base64


app = Flask(__name__)
app.config.update(
    MAIL_SERVER='email-smtp.us-west-2.amazonaws.com',
    MAIL_USE_TLS=True,
    MAIL_PORT=587,
    MAIL_USE_SSL=False,
    MAIL_USERNAME='AKIAIV7T2MQPB7WWRUSQ',
    MAIL_PASSWORD= os.environ.get('SES_MAIL_PASSWORD')
    )
# app.config.update(
#     MAIL_SERVER='smtp.mailgun.com',
#     MAIL_USE_TLS=True,
#     MAIL_PORT=587,
#     MAIL_USE_SSL=False,
#     MAIL_USERNAME='postmaster@mail.livebooth.xyz',
#     MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD')
#     )
# app.config.update(
#     MAIL_SERVER='smtp.mailgun.com',
#     MAIL_USE_TLS=True,
#     MAIL_PORT=587,
#     MAIL_USE_SSL=False,
#     MAIL_USERNAME='postmaster@livebooth.xyz',
#     MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD2')
#     )
# app.config.update(
#     MAIL_SERVER='mail.smtp2go.com',
#     MAIL_USE_TLS=True,
#     MAIL_PORT=2525,
#     MAIL_USE_SSL=False,
#     MAIL_USERNAME='austinbrown34@gmail.com',
#     MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD3')
#     )
mail = Mail(app)


def build_attachment1(filepath):
    """Build attachment mock."""
    attachment = Attachment()
    with open(filepath, "rb") as f:
        encodedMp4 = base64.b64encode(f.read())
        print(encodedMp4.decode())
        attachment.content = (encodedMp4.decode())
        attachment.type = "video/mp4"
        attachment.filename = "socialgif.mp4"
        attachment.disposition = "attachment"
        attachment.content_id = "Social GIF"
    return attachment


def build_response(resp_dict, status_code):
    response = Response(json.dumps(resp_dict), status_code)
    return response


@task
def mail_video(email, url, filepath):
    with app.app_context():
        print("about to mail")
        msg = Message('Your Social Shareable GIF',
                      sender="team@livebooth.xyz",
                      recipients=[email])

        file_type = 'video/mp4'
        msg.body = 'Download and use this version of the GIF to post to your Social Networks!'
        # msg.html = data['body'] + ' <a href="' + data['url'] + '">' + data['url'] + '</a>'
        # r = requests.get(data['url'], allow_redirects=True)
        # with open(os.path.join('/tmp', name), 'wb') as imagefile:
        #     imagefile.write(r.content)
        print("about to attach")
        with app.open_resource(filepath) as fp:
            msg.attach('socialgif.mp4', file_type, fp.read())

        print("about to send")
        # print(os.environ.get('MAIL_PASSWORD'))

        # sg = sendgrid.SendGridAPIClient(apikey=os.environ.get('SENDGRID_API_KEY'))
        # from_email = Email("team@livebooth.xyz")
        # to_email = Email(email)
        # subject = 'Your Social Shareable GIF'
        # content = Content("text/plain", msg.body)
        # mail = Mail(from_email, subject, to_email, content)
        # mail.add_attachment(build_attachment1(filepath))
        # response = sg.client.mail.send.post(request_body=mail.get())
        # print(response.status_code)
        # print(response.body)
        # print(response.headers)
        mail.send(msg)


def transcode(url):
    BINARIES_FOLDER = '/bin/ffmpeg'
    LAMBDA_PATH = '{}:{}{}'.format(
        os.environ.get('PATH', ''),
        os.environ.get('LAMBDA_TASK_ROOT', ''),
        BINARIES_FOLDER
    )
    LAMBDA_LD_LIBRARY_PATH = '{}{}'.format(
        os.environ.get('LAMBDA_TASK_ROOT', ''),
        BINARIES_FOLDER
    )
    os.environ['PATH'] = LAMBDA_PATH
    os.environ['LD_LIBRARY_PATH'] = LAMBDA_LD_LIBRARY_PATH
    # r = requests.get(url)
    s3 = boto3.resource('s3')

    try:
        try:
            os.remove('/tmp/{}'.format('giphy.gif'))
        except OSError:
            pass
        s3.Bucket('livebooth').download_file(url, '/tmp/giphy.gif')
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == "404":
            print("The object does not exist.")
        else:
            raise
    # open('/tmp/giphy.gif', 'wb').write(r.content)
    try:
        os.remove('/tmp/{}'.format('video.mp4'))
    except OSError:
        pass
    subprocess.call(['ffmpeg',  '-i', '/tmp/giphy.gif',  '-movflags', 'faststart', '-pix_fmt', 'yuv420p', '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2', '/tmp/video.mp4'])
    try:
        os.remove('/tmp/{}'.format('output.mp4'))
    except OSError:
        pass
    mbs = os.path.getsize('/tmp/video.mp4')/(1024*1024.0)
    iterations = round(7/mbs)
    try:
        os.remove('/tmp/{}'.format('list.txt'))
    except OSError:
        pass
    with open('/tmp/list.txt', 'w') as f:
        for i in range(iterations):
            f.write("file '/tmp/video.mp4'\n")
    subprocess.call(['ffmpeg', '-f', 'concat', '-safe', '0', '-i', '/tmp/list.txt', '-c', 'copy', '/tmp/output.mp4'])
    session = boto3.Session()
    s3 = session.resource('s3')
    filename = 'converted/{}.mp4'.format(uuid.uuid4().hex)
    s3.meta.client.upload_file(
        '/tmp/output.mp4', 'livebooth', filename, {'ACL': 'public-read', 'ContentType': 'video/mp4'}
    )
    conversion = {
        'url': 'https://s3.amazonaws.com/livebooth/' + filename,
        'file': '/tmp/output.mp4'
    }
    return conversion


@task
def convert_and_send(data):
    with app.app_context():
        conversion = transcode(data['url'])
        mail_video(data['email'], conversion['url'], conversion['file'])


@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)


@app.route('/')
def transcoder():
    return "Live Booth Transcoder"


@app.route('/test')
def test():
    print("about to mail")
    msg = Message('Your Social Shareable GIF',
                  sender="team@livebooth.xyz",
                  recipients=['austinbrown34@hotmail.com'])

    file_type = 'video/mp4'
    msg.body = 'Download and use this version of the GIF to post to your Social Networks!'
    # msg.html = data['body'] + ' <a href="' + data['url'] + '">' + data['url'] + '</a>'
    # r = requests.get(data['url'], allow_redirects=True)
    # with open(os.path.join('/tmp', name), 'wb') as imagefile:
    #     imagefile.write(r.content)
    print("about to attach")
    # with app.open_resource(filepath) as fp:
    #     msg.attach('socialgif.mp4', file_type, fp.read())

    print("about to send")
    # print(os.environ.get('MAIL_PASSWORD'))

    # sg = sendgrid.SendGridAPIClient(apikey=os.environ.get('SENDGRID_API_KEY'))
    # from_email = Email("team@livebooth.xyz")
    # to_email = Email(email)
    # subject = 'Your Social Shareable GIF'
    # content = Content("text/plain", msg.body)
    # mail = Mail(from_email, subject, to_email, content)
    # mail.add_attachment(build_attachment1(filepath))
    # response = sg.client.mail.send.post(request_body=mail.get())
    # print(response.status_code)
    # print(response.body)
    # print(response.headers)
    mail.send(msg)
    return "Live Booth Transcoder"


@app.route('/v1/convert', methods=['POST'])
def convert():
    if not (request.json):
        abort(400)
    print(request.json)
    data = request.json

    convert_and_send(data)
    # thread = Thread(target=convert_and_send, args=[data])
    # thread.start()

    return build_response({"status": "success"}, 200)


if __name__ == '__main__':
    app.run()
