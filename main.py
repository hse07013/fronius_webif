#!/usr/bin/env python3

"""Entry point for the fronius_webif application."""

import json
import asyncio
import datetime as dt

from aiohttp import ClientSession
from client_middleware_xdigest_auth import XdigestAuthMiddleware
from FroniusTimeOfUse import FroniusTimeOfUseContainer, FroniusScheduleTypeEnum, WorkdayEnum, TimeOfUse

async def main():
    url = "http://192.168.178.180"
    username = "customer"
    password = "#"
    
    # Create the middleware with your credentials
    digest_auth = XdigestAuthMiddleware(login=username, password=password)

    # Pass it to the ClientSession as a tuple
    async with ClientSession(middlewares=(digest_auth,)) as session:
        # The middleware will automatically handle auth challenges
        #async with session.get(url + "/api/commands/Login") as resp:
        #    txt = await resp.text()
        #    print(txt)


        async with session.get(url + "/api/config/timeofuse", data="") as resp:
            j = await resp.json()
            timeOfUseCont = FroniusTimeOfUseContainer(parseFronius=j)
            #print(json.dumps(j, indent=2))

        payload_no_timeofuse = '{"timeofuse":[]}'

        newTimeOfUse = TimeOfUse(
            Active=True,
            Power=1100,
            ScheduleType=FroniusScheduleTypeEnum.CHARGE_MAX,
            Start=dt.time(0, 0),
            End=dt.time(23, 59),
            Workdays=WorkdayEnum.MONDAY | WorkdayEnum.TUESDAY | WorkdayEnum.WEDNESDAY |
              WorkdayEnum.THURSDAY | WorkdayEnum.FRIDAY
        )

        numRemoved, _ = timeOfUseCont.addOrReplaceEntry(newTimeOfUse)
        if numRemoved > 0:
            print(f"Removed {numRemoved} entries matching criteria.")

        payload_charge = timeOfUseCont.getJson()
 
        async with session.post(url + "/api/config/timeofuse", json=payload_charge) as resp:
            txt = await resp.text()
            print(txt)


if __name__ == "__main__":
    asyncio.run(main())
