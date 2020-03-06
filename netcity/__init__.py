import asyncio
import aiohttp
import asyncio
import datetime
import hashlib
import json
import logging
from collections import OrderedDict


API_URL = 'http://netcity.eimc.ru/webapi'
DAIRY_URL = '{api_url}/student/diary?studentId={studentId}&weekEnd={weekEnd}&weekStart={weekStart}&withLaAssigns=true&withPastMandatory=true&yearId={yearId}'
HEADERS = {
    'X-Requested-With': 'XMLHttpRequest',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Referer': 'http://netcity.eimc.ru/?AL=Y',
}
YEARID = 175

logger = logging.getLogger()
logger.setLevel(logging.INFO)

class NetCityClient():
    '''
    {
      "weekStart": "2019-10-21T00:00:00",
      "weekEnd": "2019-10-27T00:00:00",
      "weekDays": [
        {
          "date": "2019-10-25T00:00:00",
          "lessons": [
            {
              "classmeetingId": 5661220,
              "day": "2019-10-25T00:00:00",
              "number": 2,
              "room": null,
              "startTime": "08:50",
              "endTime": "09:30",
              "subjectName": "Математика",
              "assignments": [
                {
                  "mark": null,
                  "attachments": [],
                  "id": 3730337,
                  "typeId": 3,
                  "assignmentName": "№302, 304",
                  "weight": 0,
                  "dueDate": "2019-10-25T00:00:00",
                  "classMeetingId": 5661220,
                  "existsTestPlan": false
                }
              ]
            }
          ]
        }
      ],
      "pastMandatory": [],
      "laAssigns": [],
      "termName": "1 четверть",
      "className": "5г"
    }
    '''
    def __init__(self):
        self.sessions = {}
        self.headers = {}
        self.cookies = {}
        self.api_url = API_URL
        self.diary_url_format = DAIRY_URL
        self.year_id = YEARID
        self.loop = asyncio.get_event_loop()
        self.session = aiohttp.ClientSession(
            loop=self.loop,
        )
        self.studentdiary = {}


    async def _fetch(self, chat_id, url):
        if chat_id not in self.headers:
            self.headers[chat_id] = HEADERS.copy()

        if chat_id not in self.cookies:
            self.cookies[chat_id] = {}

        async with self.session.get(url, headers=self.headers[chat_id], cookies=self.cookies[chat_id]) as response:
            return await response.text()


    async def _fetch_post(self, chat_id, url, payload):
        if chat_id not in self.headers:
            self.headers[chat_id] = HEADERS.copy()

        if chat_id not in self.cookies:
            self.cookies[chat_id] = {}

        async with self.session.post(url, data=payload, headers=self.headers[chat_id], cookies=self.cookies[chat_id]) as response:
            return await response.json()


    async def auth(self, chat_id, data=None):
        if data and chat_id not in self.sessions:
            self.sessions[chat_id] = {
                'login': data['login'],
                'password': data['password']
            }

        auth_getdata = await self._fetch_post(chat_id, '{}/auth/getdata'.format(self.api_url), {})
        auth_pw2 = self._get_auth_pw2(auth_getdata.get('salt'), self.sessions[chat_id]['password'])
        auth_login_post_data = {
            'LoginType': '1',
            'cid': '2',
            'sid': '66',
            'pid': '-1',
            'cn': '3',
            'sft': '2',
            'scid': '23',
            'UN': self.sessions[chat_id]['login'],
            'PW': auth_pw2[:len(self.sessions[chat_id]['password'])],
            'lt': auth_getdata.get('lt'),
            'pw2': auth_pw2,
            'ver': auth_getdata.get('ver')
        }
        auth_login = await self._fetch_post(chat_id, '{}/login'.format(self.api_url), auth_login_post_data)
        at = auth_login.get('at')
        if at:
            self.headers[chat_id]['at'] = at


    def _get_auth_pw2(self, salt, password):
        return hashlib.md5(
            str(salt + hashlib.md5(password.encode('utf-8')).hexdigest()).encode('utf-8')
        ).hexdigest()


    async def student_diary_init(self, chat_id):
        """
        {
            "students":[{"studentId":64413,"nickName":"Лебедева Нина","className":null,"classId":0,"iupGrade":0}],
            "currentStudentId":0,
            "weekStart":"2019-11-04T00:00:00",
            "yaClass":false,
            "yaClassAuthUrl":"http://www.yaklass.ru/Account/NetSchoolGate?server=http%3a%2f%2fnetcity.eimc.ru%2f&ns_token=618637084746825780356326&ts=1572859884&nn=1789099468&sg=J6DNvbKWByNmFoVyno0c8FEvyM01",
            "newDiskToken":"",
            "newDiskWasRequest":false,
            "ttsuRl":"http://WIN-EHLA79U82BH:80/",
            "externalUrl":"http://netcity.eimc.ru/",
            "weight":false,
            "maxMark":5,
            "withLaAssigns":true
        }
        :return:
        """

        out = await self._fetch(chat_id, '{}/student/diary/init'.format(self.api_url))
        self.sessions[chat_id]['student_id'] = json.loads(out)['students'][0]['studentId']


    def _get_lessons_assignmens(self, student_id):
        if student_id not in self.studentdiary:
            yield

        for week_day, lessons in self.studentdiary[student_id].items():
            for lesson in lessons:
                if 'subjectName' not in lesson or 'assignments' not in lesson:
                    continue
                yield '{}: {}'.format(
                    lesson['subjectName'],
                    ', '.join([assignment['assignmentName'] for assignment in lesson['assignments']])
                )


    def _get_last_lessons_assignmens(self, student_id):
        if student_id not in self.studentdiary:
            yield

        today = datetime.date.today()
        time_now = datetime.datetime.now()
        for week_day, lessons in reversed(self.studentdiary[student_id].items()):
            if week_day < today:
                del self.studentdiary[student_id][week_day]
            for lesson in lessons:
                if 'subjectName' not in lesson or 'assignments' not in lesson:
                    continue
                startTime = datetime.datetime.combine(today,
                                                      datetime.datetime.strptime(lesson['startTime'], '%H:%M').time())
                if time_now < startTime:
                    continue
                yield '{}: {}'.format(
                    lesson['subjectName'],
                    ', '.join([assignment['assignmentName'] for assignment in lesson['assignments']])
                )


    async def _update_assignment_week(self, student_id, chat_id=None):
        today = datetime.date.today()
        end_of_week = today + datetime.timedelta(days=today.weekday(), weeks=1)
        await self.__update_assignment(student_id, str(today), str(end_of_week), chat_id=chat_id)


    async def _update_assignment_today(self, student_id):
        today = str(datetime.date.today())
        await self.__update_assignment(student_id, today, today)


    async def __update_assignment(self, student_id, week_start, week_end, chat_id=None):
        studentdiary_url = self.diary_url_format.format(
            api_url=self.api_url,
            studentId=student_id,
            weekStart=week_start,
            weekEnd=week_end,
            yearId=self.year_id
        )

        html = await self._fetch(chat_id, studentdiary_url)
        if html == 'Ошибка доступа':
            logger.error('access error')
            logger.error(html)
            await self.auth(chat_id)
            html = await self._fetch(chat_id, studentdiary_url)

        diary = json.loads(html)
        for week_day in diary['weekDays']:
            if student_id not in self.studentdiary:
                self.studentdiary[student_id] = OrderedDict()
            self.studentdiary[student_id][datetime.datetime.strptime(week_day['date'], '%Y-%m-%dT%H:%M:%S').date()] = week_day['lessons']

    async def get_assignments_today(self, chat_id):
        await self._update_assignment_week(self.sessions[chat_id]['student_id'], chat_id=chat_id)
        return list(self._get_last_lessons_assignmens(self.sessions[chat_id]['student_id']))