import re
from astrbot.api.star import Context, Star, register
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter


@register("astrbot_plugin_llm_condenser", "Administrator", "简化LLM回复，保留核心信息与情绪", "v1.0.0", "")
class LLMCondenser(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.enabled = config.get("enabled", True)
        self.max_length = config.get("max_length", 800)
        self.debug = config.get("debug", False)
        logger.info("LLM Condenser 插件已加载")

    FILLER_PATTERNS = [
        (r'作为(一个|一名|AI|人工智能)?助[手理][，,]?\s*', ''),
        (r'我个人?[觉认]?得[呢吧]?[，,]?\s*', ''),
        (r'我(个人|自己)?认为[，,]?\s*', ''),
        (r'在我看[来][，,]?\s*', ''),
        (r'据我所知[，,]?\s*', ''),
        (r'(我)?想说的是[，,]?\s*', ''),
        (r'不得[不]?[说说提][，,]?\s*', ''),
        (r'值得[一]?提的是[，,]?\s*', ''),
        (r'总的?[来]?[说讲][，,]?\s*', ''),
        (r'总[而]?而言之[，,]?\s*', ''),
        (r'简单[来地]?[说讲][，,]?\s*', ''),
        (r'换[句种]?话说[，,]?\s*', ''),
        (r'也就是[说][，,]?\s*', ''),
        (r'当[然确][，,]?', ''),
        (r'毫[无]?疑问[，,]?\s*', ''),
        (r'不用[说疑][，,]?\s*', ''),
        (r'众[所]?周知[，,]?\s*', ''),
        (r'(那么|然后|接下来)[，,]?\s*', ''),
        (r'嗯[啊嗯呀哦]*[，,]?\s*', ''),
        (r'呃[嗯啊]*[，,]?\s*', ''),
        (r'[（(][哈哈嘿嘿嘻嘻呵呵大笑][)）]', ''),
        (r'\b(As an? (AI|language) (assistant|model),?\s*)', ''),
        (r'\b(I (think|believe|feel|suppose|guess|would say),?\s*)', ''),
        (r'\b(In my (opinion|view|experience),?\s*)', ''),
        (r'\b(To be honest|Honestly|Frankly speaking),?\s*', ''),
        (r"\b(That'?s a great question[.!]?\s*)", ''),
        (r'\b(Let me (think|explain|break this down)[.!]?\s*)', ''),
        (r"\b(It'?s (important|worth) (to note|noting|mentioning) that,?\s*)", ''),
    ]

    TIGHTEN_PATTERNS = [
        (r'非常非[常]+', '非常'),
        (r'真的非常', '非常'),
        (r'特别特[别]+', '特别'),
        (r'超级超[级]+', '超级'),
        (r'十分非常', '非常'),
        (r'真的真[的]+', '真的'),
        (r'(very\s+)+very', 'very'),
        (r'(really\s+)+really', 'really'),
        (r'so\s+so\s+', 'so '),
        (r'(extremely\s+)+extremely', 'extremely'),
    ]

    EMOTION_MARKERS = [
        '！', '!!', '…', '~',
        '哈哈', '嘿嘿', '嘻嘻', '呜呜',
        '哎呀', '天哪', '哇塞', '太棒', '太好了', '真不错',
        '❤', '😊', '😢', '😭', '🥰', '😍', '🎉', '✨',
        'lol', 'haha', 'wow', 'omg', 'XD', ':D', ':P',
        '感动', '开心', '难过', '激动', '兴奋', '悲伤', '愤怒',
        '辛苦了', '加油', '恭喜', '遗憾', '可惜', '惊讶',
    ]

    def _has_emotion(self, text: str) -> bool:
        return any(m in text for m in self.EMOTION_MARKERS)

    def _condense(self, text: str) -> str:
        if not text or not self.enabled:
            return text

        original_len = len(text)
        result = text.strip()

        for pattern, replacement in self.FILLER_PATTERNS:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        for pattern, replacement in self.TIGHTEN_PATTERNS:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        result = re.sub(r'([。！？…])\1+', r'\1', result)
        result = re.sub(r'([，、；：])\1+', r'\1', result)
        result = re.sub(r'([.!?])\1+', r'\1', result)
        result = re.sub(r'([,;:])\1+', r'\1', result)
        result = re.sub(r'(~)\1+', r'\1', result)

        result = re.sub(r'\s+', ' ', result).strip()

        sentences = re.split(r'(?<=[。！？.!?])\s*', result)
        deduped = []
        seen = set()
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            words = re.findall(r'[\u4e00-\u9fff\w]+', s.lower())
            sig = ''.join(sorted(set(words)))[:12]
            if sig and sig not in seen:
                seen.add(sig)
                deduped.append(s)
            elif not sig:
                deduped.append(s)
            elif self._has_emotion(s):
                deduped.append(s)
        result = '。'.join(deduped)
        if result and result[-1] not in '。！？.!?':
            result += '。'

        if len(result) > self.max_length:
            truncated = result[:self.max_length]
            last_punct = max(
                truncated.rfind('。'), truncated.rfind('！'),
                truncated.rfind('？'), truncated.rfind('.'),
                truncated.rfind('!'), truncated.rfind('?')
            )
            if last_punct > self.max_length * 0.6:
                result = truncated[:last_punct + 1]
            else:
                result = truncated + '…'

        if self.debug and len(result) != original_len:
            pct = (1 - len(result) / original_len) * 100
            logger.debug(f"Condensed: {original_len} -> {len(result)} chars ({pct:.0f}% reduced)")

        return result

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp):
        try:
            for attr in ('result_text', 'text', 'content', 'message'):
                if hasattr(resp, attr):
                    val = getattr(resp, attr)
                    if isinstance(val, str):
                        condensed = self._condense(val)
                        if condensed != val:
                            setattr(resp, attr, condensed)
                            if self.debug:
                                logger.debug(f"Condensed via resp.{attr}")
                        return
        except Exception as e:
            logger.warning(f"LLM Condenser error: {e}")

    @filter.command("condenser")
    async def cmd_condenser(self, event: AstrMessageEvent):
        yield event.plain_result(
            f"LLM 回复简化器\n"
            f"状态：{'已启用' if self.enabled else '已暂停'}\n"
            f"最大长度：{self.max_length} 字符\n"
            f"调试模式：{'开' if self.debug else '关'}"
        )
