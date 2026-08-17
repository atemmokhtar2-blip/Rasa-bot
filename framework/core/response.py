from framework.core.models import ActionResult, OutgoingResponse, PolicyResult

class ResponseBuilder:
    def build(self, policy: PolicyResult, action: ActionResult | OutgoingResponse | None = None) -> OutgoingResponse:
        if isinstance(action, OutgoingResponse): return action
        if isinstance(action, ActionResult):
            if action.response is not None: return action.response
            if action.success and action.data is not None: return OutgoingResponse(metadata={"data": action.data, **action.metadata})
            if action.error: return OutgoingResponse(text="تعذر تنفيذ الطلب.", metadata={"error": action.error, **action.metadata})
        if policy.decision == "ASK_CLARIFICATION": return OutgoingResponse(text="أحتاج إلى تفاصيل إضافية لتنفيذ الطلب.")
        if policy.decision == "FALLBACK": return OutgoingResponse(text="لم أفهم الطلب بشكل كافٍ. هل يمكنك توضيحه؟")
        if policy.decision == "RETURN_RESPONSE": return OutgoingResponse(metadata=policy.metadata)
        return OutgoingResponse()
