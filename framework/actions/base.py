from framework.core.interfaces import Action
from framework.core.models import OutgoingResponse

class StartAction(Action):
    name = "start"
    async def execute(self, context):
        return OutgoingResponse(text="أهلًا بك في AI Developer Framework.")

class HelpAction(Action):
    name = "help"
    async def execute(self, context):
        return OutgoingResponse(text="يمكنك إرسال طلبك باللغة الطبيعية، وسأحاول فهمه ومساعدتك.")
