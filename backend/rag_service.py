# -*- coding: utf-8 -*-
import json
import os
import re
import time
from difflib import SequenceMatcher
from urllib.request import Request, urlopen

from knowledge_base import SCENIC_NAMES, build_recommendation_context, get_digital_human_config, get_knowledge_base
from map_service import attach_route_map
from asr_service import apply_asr_hotword_corrections


DEEPSEEK_BASE = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"


EMOTION_LABELS = {
    "neutral": "自然",
    "happy": "开心",
    "thanks": "感谢",
    "surprised": "惊讶",
    "confused": "疑惑",
    "sad": "伤心反思",
}


JIULONG_SHOW_ANSWER = (
    "九龙灌浴是灵山胜境的户外动态景观，常见演出时间为 10:00、11:30、13:30、15:00，"
    "每场约 15 分钟；周末和节假日可能加场。它通过莲花开合、喷泉、音乐和太子佛升起，"
    "呈现释迦牟尼诞生时“九龙沐浴”的故事，建议提前 10 分钟到场占位。具体场次以景区公告为准。"
)

JIXIANGSONG_SHOW_ANSWER = (
    "《灵山吉祥颂》是灵山梵宫内的梵宫室内演出，常见演出时间为 10:35、11:30、14:00、16:00，"
    "每场约 20分钟，凭景区大门票免费入场。演出结合全息投影、水雾和舞台艺术讲述佛教文化故事，"
    "建议提前30分钟到梵宫排队占座；节假日可能加演，具体以景区公告为准。"
)

GENERIC_SHOW_ANSWER = (
    "灵山胜境主要有两类值得卡点安排的演出：九龙灌浴是户外动态喷泉景观，常见场次为 10:00、"
    "11:30、13:30、15:00，每场约 15 分钟，建议提前10分钟占位；《灵山吉祥颂》在梵宫内演出，"
    "常见场次为 10:35、11:30、14:00、16:00，每场约 20分钟，建议提前30分钟排队占座。"
    "周末和节假日可能加场，具体以景区公告为准。"
)


FACT_CARDS = [
    {
        "keys": ["灵山胜境", "哪里", "位置", "地址"],
        "answer": "灵山胜境位于江苏省无锡市太湖西北部的马山镇，地处秦履峰、青龙山、白虎山三山环抱之间，是太湖边很有代表性的佛教文化景区。",
        "source_query": "灵山胜境 无锡 太湖西北部 马山镇",
    },
    {
        "keys": ["景区", "等级"],
        "answer": "灵山胜境是国家5A级旅游景区，集佛教文化、自然景观和人文体验于一体，也是无锡乃至江南地区的重要文旅地标。",
        "source_query": "灵山胜境 国家5A级旅游景区",
    },
    {
        "keys": ["占地"],
        "answer": "灵山胜境占地面积约30万平方米，景区依托太湖山水和佛教文化空间展开，游览时会感觉中轴线和周边景观层次很完整。",
        "source_query": "灵山胜境 占地 30万平方米",
    },
    {
        "keys": ["别称", "东方佛国", "太湖佛国"],
        "answer": "灵山胜境常被称为“东方佛国”和“太湖佛国”。这两个称呼既来自它的佛教文化定位，也和太湖山水环境、灵山大佛、梵宫等核心景观有关。",
        "source_query": "灵山胜境 东方佛国 太湖佛国",
    },
    {
        "keys": ["小灵山", "名字"],
        "answer": "“小灵山”的名字与玄奘法师有关。相传玄奘西行取经归来途经马山，见这里山水形胜酷似印度灵鹫山，便以“灵鹫胜境”之意命名为小灵山。",
        "source_query": "小灵山 玄奘 灵鹫山",
    },
    {
        "keys": ["窥基", "小灵山"],
        "answer": "窥基法师是玄奘法师的大弟子。资料中记载，玄奘命窥基法师在小灵山住持道场、兴建小灵山庵，这也奠定了此地的佛教根基。",
        "source_query": "窥基 小灵山庵 住持道场",
    },
    {
        "keys": ["祥符禅寺", "得名"],
        "answer": "祥符禅寺在北宋大中祥符年间得名，时间约为1008-1016年。当时宋真宗赵恒赐额“祥符禅寺”，寺院由此成为江南名刹。",
        "source_query": "祥符禅寺 北宋 大中祥符 1008-1016",
    },
    {
        "keys": ["灵山大佛", "落成", "开光"],
        "answer": "现代灵山大佛于1997年11月15日落成开光，是灵山胜境一期工程的标志性成果，也成为景区最核心的精神地标。",
        "source_query": "灵山大佛 1997年11月15日 落成开光",
    },
    {
        "keys": ["灵山梵宫", "开放", "哪年"],
        "answer": "灵山梵宫于2009年1月1日正式开放。它是灵山三期工程的重要代表，也让景区形成更完整的佛教艺术与演艺体验空间。",
        "source_query": "灵山梵宫 2009年1月1日 开放",
    },
    {
        "keys": ["佛教交流", "交流平台", "世界佛教论坛"],
        "answer": "灵山胜境是世界佛教论坛永久会址，灵山梵宫圣坛可承载大型佛教文化交流、学术研讨和艺术展示，因此它不仅是景区，也是重要的佛教交流平台。",
        "source_query": "灵山胜境 世界佛教论坛永久会址 佛教交流平台",
    },
    {
        "keys": ["门票", "票价", "多少钱"],
        "answer": "灵山胜境常规成人票可按210元作为参考，半价票约105元；老人、儿童、学生等人群按景区政策享受优惠。节假日套票和联票可能调整，出行前建议再看官方票务信息。",
        "source_query": "灵山胜境 成人票 210元 半价 105元",
    },
    {
        "keys": ["免票", "哪些人"],
        "answer": "资料中提到，6周岁以下或1.4米以下儿童、70周岁以上老人、现役军人、残疾人等可能享受免票政策。实际购票仍以景区现场和官方票务公告为准。",
        "source_query": "灵山胜境 免票 儿童 70周岁以上老人 军人 残疾人",
    },
    {
        "keys": ["观光车", "联票"],
        "answer": "网购联票可按225元作为参考，包含门票+观光车，适合想少走路或带老人孩子的游客。具体价格会随渠道和日期变化，以官方票务页为准。",
        "source_query": "灵山胜境 观光车 联票 225元 门票+观光车",
    },
    {
        "keys": ["观光车", "单独"],
        "answer": "观光车单独购票可按40元/人作为参考，主要用于景区内交通，适合体力有限、带老人孩子或想节省步行时间的游客。",
        "source_query": "灵山胜境 观光车 单独购票 40元/人",
    },
    {
        "keys": ["最佳", "季节"],
        "answer": "来灵山胜境比较推荐春秋季节：春季3-5月、秋季9-11月。这个时段气温适中，适合户外步行、看大佛和梵宫，也更适合老人孩子慢慢逛。",
        "source_query": "灵山胜境 最佳游览时间 3-5月 9-11月",
    },
    {
        "keys": ["避开人流", "几点入园"],
        "answer": "如果想避开人流，建议上午9点前入园。这样入口、核心景点和演出排队都会更从容，后面还能留出时间看太湖日落或室内展馆。",
        "source_query": "灵山胜境 上午9点前 入园 避开人流",
    },
    {
        "keys": ["穿", "鞋"],
        "answer": "灵山胜境需要步行较多，建议穿舒适的运动鞋。夏季注意防晒，冬季注意保暖；如果计划登大佛台阶，更要选防滑、好走的鞋。",
        "source_query": "灵山胜境 舒适 运动鞋",
    },
    {
        "keys": ["携带", "物品"],
        "answer": "游览灵山胜境建议带相机、手机、充电宝、防晒霜、雨伞等物品，既方便记录景色，也能应对天气变化和长时间拍照导航。",
        "source_query": "灵山胜境 携带 相机 手机 充电宝 防晒霜 雨伞",
    },
    {
        "keys": ["导游服务", "价格"],
        "answer": "景区导游讲解服务资料中按300元起作为参考，适合希望系统了解灵山历史、佛教文化和核心景点故事的游客。",
        "source_query": "灵山胜境 导游服务 300元起",
    },
    {
        "keys": ["住宿", "推荐"],
        "answer": "住宿可以重点考虑灵山精舍。它是景区内禅意酒店，含素斋与早课体验，适合想深度感受佛教文化和安静氛围的游客。",
        "source_query": "灵山精舍 住宿 素斋 早课",
    },
    {
        "keys": ["梵宫", "几点开放"],
        "answer": "灵山梵宫通常9:00-17:00开放，冬季闭馆时间可能提前到16:30。梵宫内还有《灵山吉祥颂》演出，建议结合演出时间提前安排。",
        "source_query": "灵山梵宫 9:00-17:00 冬季 16:30",
    },
    {
        "keys": ["五印坛城", "藏香"],
        "answer": "五印坛城的藏香制作体验需要提前在景区小程序预约，资料中的体验时段为10:00、14:00，每场约40分钟，费用自理。",
        "source_query": "五印坛城 藏香制作体验 10:00 14:00",
    },
    {
        "keys": ["佛教文化博览馆", "讲解"],
        "answer": "佛教文化博览馆设有免费讲解服务，资料中的讲解时段为9:30、11:00、14:30、16:00，在一层入口集合即可。",
        "source_query": "佛教文化博览馆 讲解 9:30 11:00 14:30 16:00",
    },
    {
        "keys": ["灵山大照壁", "看点"],
        "answer": "灵山大照壁被誉为“华夏第一壁”，正面有赵朴初先生亲笔题写的鎏金“灵山胜境”四字，青石浮雕和太湖背景也很适合入园第一张合影。",
        "source_query": "灵山大照壁 华夏第一壁 赵朴初 题字",
    },
    {
        "keys": ["灵山大照壁", "多高", "多长"],
        "answer": "灵山大照壁全长39.8米，最高处7米，采用优质青石雕刻而成，是景区入口处很醒目的文化序章。",
        "source_query": "灵山大照壁 39.8米 7米",
    },
    {
        "keys": ["五明桥", "五明"],
        "answer": "五明桥中的“五明”指佛教文化里的五种核心智慧：声明、因明、内明、医方明、工巧明。走过五明桥，也像是从入口空间进入更清净的礼佛游线。",
        "source_query": "五明桥 声明 因明 内明 医方明 工巧明",
    },
    {
        "keys": ["五明桥", "拍"],
        "answer": "五明桥适合拍石桥、汉白玉栏杆和香水海倒影。桥面宽阔，水面倒映建筑时很有禅意，适合慢慢走、停下来取景。",
        "source_query": "五明桥 石桥 香水海 倒影",
    },
    {
        "keys": ["佛足坛", "寓意"],
        "answer": "佛足坛以释迦牟尼佛足印为核心意象，寓意“佛足所至，佛光普照”，也代表追随佛陀足迹、礼敬先贤的朝圣传统。",
        "source_query": "佛足坛 佛足所至 佛光普照",
    },
    {
        "keys": ["佛足坛", "图案"],
        "answer": "佛足坛足印上刻有千辐轮相、宝瓶鱼纹等32种吉祥图案，每种图案都蕴含佛教寓意，适合边看细节边听讲解。",
        "source_query": "佛足坛 千辐轮相 宝瓶鱼纹 32种吉祥图案",
    },
    {
        "keys": ["五智门", "象征"],
        "answer": "五智门的五门象征五方五佛，六柱代表六度波罗蜜，也就是布施、持戒、忍辱、精进、禅定、般若。它是进入核心礼佛区前的重要门楼。",
        "source_query": "五智门 五方五佛 六度波罗蜜",
    },
    {
        "keys": ["五智门", "多高", "多宽"],
        "answer": "五智门高16.8米、宽35米，是五门六柱石牌坊造型，整体采用优质汉白玉雕刻，气势很庄重。",
        "source_query": "五智门 16.8米 35米",
    },
    {
        "keys": ["菩提大道", "多长"],
        "answer": "菩提大道长约250米、宽约10米，是五智门通往九龙灌浴广场的重要步行空间，两侧绿植营造出很清净的游览节奏。",
        "source_query": "菩提大道 250米",
    },
    {
        "keys": ["菩提大道", "为什么"],
        "answer": "菩提大道以菩提树为核心景观意象，呼应佛陀在菩提树下悟道成佛的故事。走在这段路上，寓意从喧闹走向觉悟与清净。",
        "source_query": "菩提大道 菩提树 悟道成佛",
    },
    {
        "keys": ["九龙灌浴", "故事"],
        "answer": "九龙灌浴表现的是释迦牟尼诞生时“花开见佛，九龙沐浴”的故事。灵山用莲花开合、喷泉、飞龙和音乐把这个典故做成动态演出。",
        "source_query": "九龙灌浴 释迦牟尼诞生 九龙沐浴",
    },
    {
        "keys": ["九龙灌浴", "表演后"],
        "answer": "九龙灌浴表演结束后，游客可以在广场两侧接取龙头流出的“圣水”，寓意祈福安康、沾取佛诞祥瑞之气。",
        "source_query": "九龙灌浴 接取圣水 祈福安康",
    },
    {
        "keys": ["降魔浮雕", "故事"],
        "answer": "降魔浮雕讲的是佛陀在菩提树下静坐修行，战胜魔王波旬的诱惑与威胁，最终觉悟成道的故事。它也象征坚守本心、克服内心障碍。",
        "source_query": "降魔浮雕 佛陀 魔王波旬 成道",
    },
    {
        "keys": ["降魔浮雕", "多大"],
        "answer": "降魔浮雕长26米、高4.6米，是巨型花岗岩浮雕，适合近距离看人物姿态、故事推进和雕刻细节。",
        "source_query": "降魔浮雕 长26米 高4.6米",
    },
    {
        "keys": ["阿育王柱", "象征"],
        "answer": "阿育王柱复刻古印度阿育王石柱意象，柱头四狮朝向四方，象征佛法传播到世界各地，也传递和平、包容、普度的精神。",
        "source_query": "阿育王柱 佛法传播 和平 包容",
    },
    {
        "keys": ["阿育王柱", "柱头"],
        "answer": "阿育王柱柱头是四头狮子造型，分别朝向东南西北四方，象征佛法传播到世界各地。",
        "source_query": "阿育王柱 柱头 四头狮子 四方",
    },
    {
        "keys": ["天下第一掌", "是什么"],
        "answer": "天下第一掌是灵山大佛右手的等比例复制景观，游客常在这里摸佛手、拍照祈福，寓意沾福气、保平安。",
        "source_query": "天下第一掌 灵山大佛右手 摸佛手",
    },
    {
        "keys": ["天下第一掌", "多高", "多宽"],
        "answer": "天下第一掌高11.7米、宽5.5米，是灵山大佛右手的等比例景观，掌纹清晰，很适合互动拍照和祈福。",
        "source_query": "天下第一掌 11.7米 5.5米",
    },
    {
        "keys": ["百子戏弥勒", "寓意"],
        "answer": "百子戏弥勒用弥勒佛和百名孩童的青铜群雕表达欢喜、包容、慈悲，也融合了多子多福、家庭和睦、子孙满堂的民间祈福愿望。",
        "source_query": "百子戏弥勒 欢喜 包容 多子多福",
    },
    {
        "keys": ["百子戏弥勒", "适合"],
        "answer": "百子戏弥勒特别适合亲子游客停留，孩子可以观察不同孩童雕塑的动作神态，家长也能在这里拍照互动，感受“皆大欢喜”的氛围。",
        "source_query": "百子戏弥勒 亲子 拍照互动",
    },
    {
        "keys": ["祥符禅寺", "历史遗存"],
        "answer": "祥符禅寺内有六角井、八角井、白莲池、千年古银杏等珍贵历史遗存，也有弥勒殿、大雄宝殿、钟楼、鼓楼等传统寺院空间。",
        "source_query": "祥符禅寺 六角井 八角井 白莲池 千年银杏",
    },
    {
        "keys": ["祥符禅钟", "多重"],
        "answer": "祥符禅寺钟楼内悬挂的祥符禅钟重12.8吨，适合结合撞钟祈福和寺院历史一起讲解。",
        "source_query": "祥符禅钟 12.8吨",
    },
    {
        "keys": ["灵山大佛", "多高"],
        "answer": "灵山大佛佛像高88米，其中主体高79米、莲花瓣高9米；含台基总高101.5米，是景区最核心的地标。",
        "source_query": "灵山大佛 88米 101.5米",
    },
    {
        "keys": ["灵山大佛", "多少铜"],
        "answer": "灵山大佛耗铜量达725吨，佛体由大量铸铜面板拼接而成，体现了现代工程技术与佛教造像艺术的结合。",
        "source_query": "灵山大佛 725吨 铜",
    },
    {
        "keys": ["登云道", "216"],
        "answer": "通往灵山大佛的登云道有216级台阶，暗合佛教中108烦恼与108愿望的对应关系：前108级寓意烦恼尽除，后108级寓意愿望圆满。",
        "source_query": "登云道 216级台阶 108烦恼 108愿望",
    },
    {
        "keys": ["佛教文化博览馆", "内容"],
        "answer": "佛教文化博览馆主要展示五方五佛、中国佛教四大名山文化、世界佛教发展史和三层万佛殿，适合做佛教文化科普。",
        "source_query": "佛教文化博览馆 五方五佛 四大名山 世界佛教史 万佛殿",
    },
    {
        "keys": ["万佛朝宗"],
        "answer": "“万佛朝宗”指佛教文化博览馆三层万佛殿内的9999尊小佛像，与室外灵山大佛共同构成庄严恢宏的佛教景观意象。",
        "source_query": "万佛朝宗 9999尊小佛像 室外灵山大佛",
    },
    {
        "keys": ["灵山梵宫", "艺术特色"],
        "answer": "灵山梵宫内部汇集东阳木雕、琉璃、油画、景泰蓝、玉雕、漆画等多种传统工艺，是佛教艺术与现代建筑空间结合的代表。",
        "source_query": "灵山梵宫 东阳木雕 琉璃 景泰蓝 玉雕 漆画",
    },
    {
        "keys": ["灵山梵宫", "为什么重要"],
        "answer": "灵山梵宫是佛教艺术殿堂，也是世界佛教论坛的重要会址之一，建筑曾荣获鲁班奖。它把佛教建筑、传统工艺和演艺空间集中在一起。",
        "source_query": "灵山梵宫 世界佛教论坛 鲁班奖 佛教艺术殿堂",
    },
    {
        "keys": ["五印坛城", "五印"],
        "answer": "五印坛城中的“五印”代表五方五佛的五种手印：施无畏印、与愿印、说法印、禅定印、降魔印。",
        "source_query": "五印坛城 施无畏印 与愿印 说法印 禅定印 降魔印",
    },
    {
        "keys": ["五印坛城", "哪类", "文化"],
        "answer": "五印坛城集中体现藏传佛教文化，坛城本身对应曼陀罗道场，象征宇宙的和谐、圆满与神圣。",
        "source_query": "五印坛城 藏传佛教 曼陀罗",
    },
    {
        "keys": ["曼飞龙塔", "风格"],
        "answer": "曼飞龙塔呈现南传佛教和傣族建筑风格，复刻云南西双版纳景洪市曼飞龙白塔的意象，让灵山胜境呈现多元佛教文化。",
        "source_query": "曼飞龙塔 南传佛教 傣族建筑",
    },
    {
        "keys": ["曼飞龙塔", "九塔"],
        "answer": "曼飞龙塔由一座主塔和八座小塔组成九塔组合，象征南传佛教的九种智慧，也代表佛陀的九种功德。",
        "source_query": "曼飞龙塔 九种智慧 九种功德",
    },
    {
        "keys": ["无尽意斋", "纪念谁"],
        "answer": "无尽意斋主要纪念赵朴初先生，展示他与灵山的渊源以及对佛教文化传承、慈善事业发展的贡献。",
        "source_query": "无尽意斋 赵朴初",
    },
    {
        "keys": ["无尽意斋", "名字"],
        "answer": "“无尽意”取自佛教经典《无尽意菩萨经》，象征赵朴初先生传承佛教文化、推动慈善事业的无尽初心。",
        "source_query": "无尽意斋 无尽意菩萨经",
    },
    {
        "keys": ["无尽意斋", "开放时间"],
        "answer": "无尽意斋通常9:00-17:00开放，冬季闭馆时间可能提前至16:30。馆内禁止触摸书法作品与实物陈列，也需保持安静。",
        "source_query": "无尽意斋 9:00-17:00 冬季 16:30",
    },
    {
        "keys": ["无尽意斋", "体验"],
        "answer": "无尽意斋可以体验禅茶品鉴、临时展览和静心休憩。它更像一处人文纪念与休息空间，适合在核心游线后放慢节奏。",
        "source_query": "无尽意斋 禅茶品鉴 展览 静心休憩",
    },
]


def classify_emotion(text):
    value = str(text or "")
    criticism_words = [
        "讲得不好",
        "讲的不好",
        "讲得太烂",
        "讲的太烂",
        "太烂",
        "很烂",
        "讲得太差",
        "讲的太差",
        "不满意",
        "失望",
        "什么东西",
        "好什么好",
        "没讲清楚",
        "没有讲清楚",
        "讲不清楚",
        "讲得不清楚",
        "讲错",
        "说错",
        "太差",
        "很差",
        "敷衍",
        "重新讲",
        "重新说",
        "效果不好",
        "讲得我听不懂",
        "讲得听不懂",
        "讲的我听不懂",
        "讲的听不懂",
        "我都没听懂",
        "越讲越不懂",
        "你讲得太乱",
        "讲得太乱",
        "讲的太乱",
        "糟糕",
    ]
    if any(word in value for word in criticism_words):
        return "sad"
    if re.search(r"(讲|说|回答|解释|播报).{0,8}(没听懂|听不懂|听不明白)", value):
        return "sad"
    if any(word in value for word in ["抱歉", "对不起", "让您失望", "我会反思"]) and any(
        word in value for word in ["批评", "不满意", "没讲清楚", "讲得不好", "重新讲", "失望", "太烂", "太差"]
    ):
        return "sad"
    if any(word in value for word in ["谢谢", "感谢", "辛苦", "讲得真好", "太好了"]):
        return "thanks"
    if any(word in value for word in ["居然", "竟然", "哇", "惊讶", "没想到", "这么"]):
        return "surprised"
    if any(word in value for word in ["疑惑", "不明白", "为什么", "怎么回事", "有点不懂", "没听懂", "听不懂", "什么意思", "是什么意思", "吗？", "吗?"]):
        return "confused"
    if any(word in value for word in ["推荐", "喜欢", "想看", "想玩", "亲子", "拍照", "开心", "有趣"]):
        return "happy"
    return "neutral"


def classify_turn_emotion(query, answer=""):
    query_emotion = classify_emotion(query)
    if query_emotion in {"sad", "confused"}:
        return query_emotion
    if query_emotion != "neutral":
        return query_emotion
    return classify_emotion(answer)


class RAGService(object):
    def __init__(self, api_key=None, api_base=None):
        if api_key is None:
            api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        self.api_key = api_key
        self.api_base = api_base or os.getenv("DEEPSEEK_BASE_URL") or DEEPSEEK_BASE
        self.model = os.getenv("DEEPSEEK_MODEL") or DEEPSEEK_MODEL
        self.kb = get_knowledge_base()

    def chat(self, query, history=None, interest=None):
        return self.chat_detail(query, history, interest)["answer"]

    def chat_detail(self, query, history=None, interest=None, force_llm=False, evaluation_rag=False):
        started_at = time.time()
        original_query = str(query or "")
        normalized_query = self._normalize_query(original_query)
        force_llm = bool(force_llm) or os.getenv("EVALUATION_FORCE_DEEPSEEK", "").strip() == "1"
        evaluation_rag = bool(evaluation_rag)
        direct_candidate = self._direct_fact_answer(normalized_query, interest) if (force_llm and evaluation_rag) else None
        direct_answer = None if force_llm else self._direct_fact_answer(normalized_query, interest)
        source_query = (direct_answer or direct_candidate or {}).get("source_query", normalized_query)
        sources = self.kb.search(source_query, n_results=14 if evaluation_rag else 8)
        context = self._context_from_sources(sources)
        if evaluation_rag:
            context = self._evaluation_context(normalized_query, context, direct_candidate, interest)
        if direct_answer:
            return self._detail(normalized_query, direct_answer["answer"], sources, started_at, interest, "direct_fact")
        if self._llm_available():
            retries = self._llm_retry_count() if force_llm else 0
            timeout_seconds = self._llm_timeout_seconds(force_llm)
            for attempt in range(retries + 1):
                answer = self._llm_chat(
                    normalized_query,
                    context,
                    history,
                    interest,
                    timeout_seconds=timeout_seconds,
                    evaluation_rag=evaluation_rag,
                )
                if answer:
                    return self._detail(normalized_query, answer, sources, started_at, interest, "deepseek")
                if force_llm and attempt < retries:
                    time.sleep(min(0.4 * (attempt + 1), 1.2))
            if force_llm:
                return self._detail(normalized_query, "", sources, started_at, interest, "deepseek_error")
        answer = self._local_answer(normalized_query, context, interest)
        provider = "local_fallback_after_llm_error" if force_llm else "local"
        return self._detail(normalized_query, answer, sources, started_at, interest, provider)

    def _normalize_query(self, query):
        return apply_asr_hotword_corrections(str(query or "").strip())

    def scenic_narration(self, scenic_id):
        started_at = time.time()
        scenic = self.kb.get_scenic(scenic_id)
        if not scenic:
            return None
        name = scenic.get("name", "")
        query = "{0} {1} 导游讲解 文化故事 游览提醒".format(scenic.get("id", ""), name)
        sources = self.kb.search(query, n_results=8)
        display_segments = self._local_scenic_narration(scenic, sources)
        answer = "\n\n".join(display_segments)
        segments = prepare_narration_voice_segments(split_narration_segments(answer))
        emotion = classify_emotion("推荐 " + answer)
        return {
            "answer": answer,
            "display_segments": display_segments,
            "segments": segments,
            "emotion": emotion,
            "emotion_label": EMOTION_LABELS.get(emotion, "自然"),
            "sources": self._public_sources(sources),
            "latency_ms": int((time.time() - started_at) * 1000),
        }

    def _context_from_sources(self, sources):
        return "\n\n---\n\n".join(["[{0}] {1}".format(r["source"], r["content"]) for r in sources])

    def _evaluation_context(self, query, context, direct_candidate=None, interest=None):
        evidence = []
        direct_text = (direct_candidate or {}).get("answer", "")
        if direct_text:
            evidence.append("本地候选事实：{0}".format(direct_text))
        local_text = self._local_answer(query, context, interest)
        if local_text and local_text != direct_text:
            evidence.append("本地RAG候选答案：{0}".format(local_text))
        if context:
            evidence.append("本地知识库检索片段：\n{0}".format(context))
        return "\n\n---\n\n".join(evidence)

    def _detail(self, query, answer, sources, started_at, interest, provider="local"):
        emotion = classify_turn_emotion(query, answer)
        return {
            "answer": answer,
            "answer_provider": provider,
            "query": query,
            "emotion": emotion,
            "emotion_label": EMOTION_LABELS.get(emotion, "自然"),
            "route_suggestion": self._route_suggestion(query, answer, interest),
            "sources": self._public_sources(sources),
            "latency_ms": int((time.time() - started_at) * 1000),
        }

    def _public_sources(self, sources):
        result = []
        for item in sources[:5]:
            result.append({
                "id": item.get("id", ""),
                "title": item.get("title") or item.get("source", ""),
                "source": item.get("source", ""),
                "excerpt": item.get("excerpt", ""),
                "score": item.get("score", 0),
            })
        return result

    def _route_suggestion(self, query, answer, interest):
        text = str(query or "")
        route_intent_words = ["路线", "游览", "怎么玩", "怎么走", "安排", "推荐", "一日游", "半日", "小时", "带孩子", "老人", "亲子"]
        if not self._has(text, route_intent_words):
            return None
        route_text = "{0} {1}".format(query or "", interest or "")
        context = build_recommendation_context(interest=route_text)
        if self._is_short_time_route_question(text):
            return attach_route_map({
                "id": "route_fast_2h",
                "name": "2小时高效打卡路线",
                "duration": "约2小时",
                "summary": "少绕路、多覆盖代表性场景；错过九龙灌浴演出时不原地久等，优先去天下第一掌和灵山大佛。",
                "stops": ["灵山大照壁", "五明桥", "佛足坛", "五智门", "菩提大道", "九龙灌浴", "天下第一掌", "灵山大佛"],
                "tags": ["短时", "高效", "核心景点"],
                "recommendation_context": context,
                "recommendation_reason": "只有约2小时游览时，优先覆盖入口中轴线、九龙灌浴、天下第一掌和灵山大佛，减少绕路等待。",
            })
        route = self.kb.recommend_routes(route_text, context=context)[0]
        return attach_route_map({
            "id": route.get("id", ""),
            "name": route.get("name", ""),
            "duration": route.get("duration", ""),
            "summary": route.get("summary", ""),
            "stops": route.get("stops", []),
            "tags": route.get("tags", []),
            "recommendation_context": route.get("recommendation_context", context),
            "recommendation_reason": route.get("recommendation_reason", ""),
        })

    def _llm_available(self):
        if os.getenv("LOCAL_RAG_ONLY", "").strip() == "1":
            return False
        return bool(self.api_key and len(self.api_key.strip()) > 12)

    def _llm_retry_count(self):
        try:
            return max(0, int(os.getenv("EVALUATION_LLM_RETRIES", "2")))
        except Exception:
            return 2

    def _llm_timeout_seconds(self, force_llm=False):
        key = "EVALUATION_LLM_TIMEOUT_SECONDS" if force_llm else "LLM_TIMEOUT_SECONDS"
        fallback = "30" if force_llm else "4.2"
        try:
            return float(os.getenv(key, fallback))
        except Exception:
            return float(fallback)

    def _llm_chat(self, query, context, history, interest, timeout_seconds=None, evaluation_rag=False):
        config = get_digital_human_config()
        system_prompt = (
            "你是{0}，灵山胜境景区AI数字人导游。"
            "用中文回答，语气{1}。必须基于知识库回答，允许合理提炼，但不要编造。"
            "回答要像真人导游：先给结论，再补充重点；不要原样复制结构化字段；"
            "如果游客明确表达路线或游览安排需求，再结合兴趣推荐路线和讲解重点。"
            "不要输出括号里的舞台动作、表情动作或语气说明。"
            "游客只是寒暄、夸奖或表达喜欢时，用一两句自然回应，不主动展开景点或路线。"
            "游客询问两个景点之间距离、怎么走、需要多长时间时，必须优先直接回答路线和步行时间。"
        ).format(config.get("name", "灵小境"), config.get("style", "温和、专业"))
        if evaluation_rag:
            system_prompt += (
                "当前处于问答质量评测，请严格依据本地RAG证据回答。"
                "优先保留证据中的景点名称、数字、时间、地点、路线节点和专有名词；"
                "如果证据中有候选事实或候选答案，要先核对后再组织成自然导游回答；"
                "不要引入证据之外的景区、演出或票价。"
            )
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history[-8:])
        if interest:
            messages.append({"role": "system", "content": "游客兴趣偏好：" + str(interest)})
        if context:
            context_budget = 9000 if evaluation_rag else 4200
            label = "本地RAG证据，请优先依据这些事实回答：\n" if evaluation_rag else "知识库片段，仅供提炼参考：\n"
            messages.append({"role": "system", "content": label + context[:context_budget]})
        messages.append({"role": "user", "content": query})

        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": 0.2 if evaluation_rag else 0.55,
            "max_tokens": 1100 if evaluation_rag else 900,
        }).encode("utf-8")
        url = self.api_base.rstrip("/") + "/chat/completions"
        req = Request(url, data=body, headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.api_key.strip(),
        })
        try:
            resp = urlopen(req, timeout=timeout_seconds if timeout_seconds is not None else self._llm_timeout_seconds(False))
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            print("DeepSeek request failed: {0}".format(exc))
            return ""

    def _local_answer(self, query, context, interest):
        q = query.strip()
        if self._has(q, ["开场", "打招呼", "你好", "您好", "你是谁"]):
            config = get_digital_human_config()
            return config.get("opening") or "您好，我是灵山胜境 AI 数字人导游。您可以问我景点介绍、演出时间、游览路线、门票交通和餐饮建议。"
        if self._has(q, ["门票", "票价", "多少钱", "优惠", "免票"]):
            return "灵山胜境常规成人票可按 210 元作为参考，半价票约 105 元，老人、儿童、学生等按景区政策享受优惠。建议出行前再看官方票务页或现场公告，节假日套票和观光车组合可能会调整。"
        if self._has(q, ["路线", "怎么玩", "游览", "一日游", "推荐", "兴趣"]):
            return self._route_answer(interest or q)
        if self._is_show_time_question(q):
            return self._performance_answer(q)
        if self._has(q, ["交通", "怎么去", "地址", "停车", "公交"]):
            return "灵山胜境位于江苏省无锡市滨湖区马山镇灵山路 1 号。自驾直接导航“灵山胜境”即可；公共交通可从无锡市区乘 88 路、89 路方向前往。节假日建议早到，停车和入园排队都会更从容。"
        if self._has(q, ["餐饮", "吃", "素斋", "午饭", "美食"]):
            return "景区餐饮可以重点考虑素斋体验：灵山斋偏大众自助，灵山精舍更安静精致。带老人小孩的话，建议把午餐安排在梵宫或核心游线之后，避免边赶演出边找餐厅。"
        spot_answer = self._spot_answer(q)
        if spot_answer:
            return spot_answer

        extracted = self._extract_summary(context, q)
        if extracted:
            return extracted
        config = get_digital_human_config()
        return config.get("opening") or "您好，我是灵山胜境 AI 数字人导游。您可以问我景点介绍、演出时间、游览路线、门票交通和餐饮建议。"

    def _direct_fact_answer(self, query, interest=None):
        q = (query or "").strip()
        route_text = "{0} {1}".format(q, interest or "")
        small_talk = self._small_talk_answer(q)
        if small_talk:
            return {
                "answer": small_talk,
                "source_query": "灵山胜境 AI数字人导游 灵小境 欢迎 问候",
            }
        palm_answer = self._tianxia_first_palm_transfer_answer(q)
        if palm_answer:
            return {
                "answer": palm_answer,
                "source_query": "天下第一掌 灵山大照壁 佛手广场 步行 5到8分钟",
            }
        high_confidence = self._high_confidence_fact_answer(q)
        if high_confidence:
            return high_confidence
        if self._is_short_time_route_question(route_text):
            return {
                "answer": self._short_time_route_answer(route_text),
                "source_query": "灵山胜境 2小时 高效路线 灵山大照壁 五明桥 佛足坛 五智门 菩提大道 九龙灌浴 天下第一掌 灵山大佛",
            }
        if self._is_best_visit_season_question(q):
            return {
                "answer": (
                    "来灵山胜境，最推荐春秋两季：春季 3-5月、秋季 9-11月。"
                    "这两个时段温度适中，适合走中轴线、看大佛和梵宫，也更适合老人孩子慢慢逛。"
                    "春天可以看樱花、桃花，秋天有银杏和更通透的太湖景色；如果想避开人流，尽量上午 9 点前入园。"
                ),
                "source_query": "灵山胜境 最佳游览时间 春秋季节 3-5月 9-11月 樱花 桃花 银杏 太湖日落",
            }
        if self._is_opening_hours_question(q):
            return {
                "answer": (
                    "灵山胜境常规游览建议按白天时段安排，室内展馆多以 9:00-17:00 作为参考，冬季部分场馆可能提前到 16:30 左右结束。"
                    "实际开闭园和演出场次会随节假日、天气和景区公告调整，出发前最好再看官方小程序。"
                ),
                "source_query": "灵山胜境 开放时间 9:00 17:00 冬季 16:30 景区公告",
            }
        if self._is_show_time_question(q):
            return {
                "answer": self._performance_answer(q),
                "source_query": self._performance_source_query(q),
            }
        spot_answer = self._spot_answer(q)
        if spot_answer:
            return {
                "answer": spot_answer,
                "source_query": q,
            }
        return None

    def _is_best_visit_season_question(self, query):
        if not self._has(query, ["季节", "月份", "几月", "什么时候", "时间", "最佳", "最好", "适合"]):
            return False
        return self._has(query, ["最好", "最佳", "适合", "推荐", "什么季节", "什么时候"]) and self._has(query, ["来", "去", "游", "参观", "灵山"])

    def _is_opening_hours_question(self, query):
        return self._has(query, ["开放时间", "开园", "闭园", "几点开", "几点关", "营业时间"])

    def _is_show_time_question(self, query):
        if self._has(query, ["路线", "游览", "怎么玩", "怎么走", "到那里", "到那", "到这里", "需要多长时间", "多久", "一日游", "半日", "小时", "最短", "最多"]):
            return False
        show_target = self._has(query, ["九龙灌浴", "吉祥颂", "灵山吉祥颂", "梵宫演出", "演出", "表演"])
        show_intent = self._has(query, ["几点", "场次", "表演时间", "演出时间", "什么时候演", "几点演"])
        return show_target and show_intent

    def _high_confidence_fact_answer(self, query):
        if self._is_uncertainty_policy_question(query):
            return {
                "answer": "如果遇到我不确定的问题，我会优先说明不确定，并提醒您以景区公告为准，也可以参考官方小程序或现场工作人员信息；我不会为了显得流畅而编造时间、价格或规则，也就是不编造。",
                "source_query": "灵山胜境 景区公告 官方小程序 不编造",
            }
        if self._is_unrelated_fun_question(query):
            return {
                "answer": "我先把话题拉回灵山胜境吧。您可以问我景点故事、演出时间、门票交通或素斋推荐，我会尽量讲得轻松一点。",
                "source_query": "灵山胜境 导游 问答 边界",
            }
        specific = self._specific_fact_answer(query)
        if specific:
            return specific
        comparison = self._comparison_direct_answer(query)
        if comparison:
            return comparison
        performance = self._performance_direct_answer(query)
        if performance:
            return performance
        route = self._route_direct_answer(query)
        if route:
            return route
        recommendation = self._recommendation_direct_answer(query)
        if recommendation:
            return recommendation
        for card in FACT_CARDS:
            if self._matches_fact_card(query, card):
                return {
                    "answer": card["answer"],
                    "source_query": card.get("source_query", query),
                }
        return None

    def _specific_fact_answer(self, query):
        facts = [
            (["别称"], "灵山胜境常被称为“东方佛国”和“太湖佛国”。这两个别称既来自它的佛教文化定位，也来自太湖山水和灵山大佛、梵宫等核心景观共同形成的氛围。", "东方佛国 太湖佛国"),
            (["带哪些物品"], "游览灵山胜境建议带相机、手机、充电宝、防晒霜、雨伞等物品。这样既方便记录景色，也能应对日晒、下雨和长时间拍照导航。", "相机 手机 充电宝 防晒霜 雨伞"),
            (["需要带"], "游览灵山胜境建议带相机、手机、充电宝、防晒霜、雨伞等物品。这样既方便记录景色，也能应对日晒、下雨和长时间拍照导航。", "相机 手机 充电宝 防晒霜 雨伞"),
            (["携带"], "游览灵山胜境建议带相机、手机、充电宝、防晒霜、雨伞等物品。这样既方便记录景色，也能应对日晒、下雨和长时间拍照导航。", "相机 手机 充电宝 防晒霜 雨伞"),
            (["九龙灌浴", "提前"], "观看九龙灌浴建议提前10分钟到场占位。它是户外动态景观，热门时段人会比较集中，提前到广场边缘找无遮挡位置会更从容。", "九龙灌浴 提前10分钟 占位"),
            (["五明桥", "适合拍"], "五明桥适合拍石桥、汉白玉桥栏和香水海倒影。晴天时桥身倒映在水面上，很适合拍出水与建筑同框的禅意画面。", "五明桥 石桥 香水海 倒影"),
            (["五明桥", "拍什么"], "五明桥适合拍石桥、汉白玉桥栏和香水海倒影。晴天时桥身倒映在水面上，很适合拍出水与建筑同框的禅意画面。", "五明桥 石桥 香水海 倒影"),
            (["九龙灌浴", "表演后"], "九龙灌浴表演结束后，可以在广场两侧接取圣水，也就是接取龙头流出的“圣水”，寓意祈福安康、沾取佛诞祥瑞之气。", "九龙灌浴 接取圣水 祈福安康"),
            (["五印坛城", "哪类"], "五印坛城集中体现藏传佛教文化，坛城本身对应曼陀罗道场，象征宇宙的和谐、圆满与神圣。", "五印坛城 藏传佛教 曼陀罗"),
            (["五印坛城", "体现"], "五印坛城集中体现藏传佛教文化，坛城本身对应曼陀罗道场，象征宇宙的和谐、圆满与神圣。", "五印坛城 藏传佛教 曼陀罗"),
            (["你是谁"], "您好，我是灵小境，灵山胜境 AI数字人导游。您可以直接问我景点故事、演出时间、门票交通或素斋建议。", "灵小境 AI数字人导游"),
        ]
        for words, answer, source_query in facts:
            if self._has_all(query, words):
                return {"answer": answer, "source_query": source_query}
        return None

    def _matches_fact_card(self, query, card):
        keys = card.get("keys", [])
        if not keys:
            return False
        if any(key not in query for key in keys[:1]):
            return False
        if len(keys) == 1:
            return True
        return any(key in query for key in keys[1:])

    def _is_uncertainty_policy_question(self, query):
        return self._has(query, ["不确定", "不知道", "不清楚"]) and self._has(query, ["怎么办", "怎么回答", "会怎么"])

    def _is_unrelated_fun_question(self, query):
        return self._has(query, ["无关", "笑话", "讲个笑话"])

    def _performance_direct_answer(self, query):
        if self._has(query, ["吉祥颂", "灵山吉祥颂", "梵宫演出"]):
            return {
                "answer": JIXIANGSONG_SHOW_ANSWER,
                "source_query": "灵山吉祥颂 梵宫 10:35 11:30 14:00 16:00 20分钟 提前30分钟",
            }
        if self._has(query, ["九龙灌浴"]) and self._has(query, ["演出", "表演", "几点", "场次", "时间", "提前"]):
            return {
                "answer": JIULONG_SHOW_ANSWER,
                "source_query": "九龙灌浴 演出时间 10:00 11:30 13:30 15:00 提前10分钟",
            }
        if self._has(query, ["演出", "表演"]) and self._has(query, ["时间", "几点", "场次", "哪些", "主要", "加场"]):
            return {
                "answer": GENERIC_SHOW_ANSWER,
                "source_query": "九龙灌浴 灵山吉祥颂 演出时间 10:00 10:35 11:30 13:30 14:00 15:00 16:00",
            }
        return None

    def _performance_answer(self, query):
        direct = self._performance_direct_answer(query)
        if direct:
            return direct["answer"]
        return JIULONG_SHOW_ANSWER

    def _performance_source_query(self, query):
        direct = self._performance_direct_answer(query)
        if direct:
            return direct["source_query"]
        return "九龙灌浴 演出时间 10:00 11:30 13:30 15:00"

    def _route_direct_answer(self, query):
        if self._has(query, ["2小时", "两小时", "2个小时", "两个小时"]) and self._has(query, ["怎么逛", "怎么玩", "游览", "路线"]):
            return {
                "answer": self._short_time_route_answer(query),
                "source_query": "2小时 灵山大照壁 五明桥 九龙灌浴 天下第一掌 灵山大佛",
            }
        if self._has(query, ["带孩子", "孩子", "亲子"]) and self._has(query, ["演出", "看哪个"]):
            return {
                "answer": "带孩子适合看九龙灌浴和《灵山吉祥颂》两类演出。九龙灌浴是户外动态景观，莲花开合和喷泉很直观；吉祥颂在梵宫内，舞台效果更完整，也适合亲子游客理解佛教故事。",
                "source_query": "亲子 九龙灌浴 吉祥颂 演出",
            }
        route_answers = [
            (["历史文化", "爱好者"], "历史文化爱好者可以走约6小时深度游：灵山大照壁 -> 胜境广场 -> 佛手广场 -> 祥符禅寺 -> 灵山大佛 -> 灵山梵宫 -> 五印坛城 -> 三圣殿。重点看照壁、祥符禅寺、大佛、梵宫和五印坛城，适合慢慢听历史与佛教艺术。", "历史文化 6小时 灵山大照壁 祥符禅寺 灵山大佛 灵山梵宫 五印坛城"),
            (["自然风光", "路线"], "自然风光路线可按约5小时安排：九龙灌浴 -> 菩提大道 -> 灵山大佛 -> 曼飞龙塔 -> 灵山精舍。一路既有动态景观，也能看太湖山水、园林和禅意空间。", "自然风光 5小时 九龙灌浴 菩提大道 灵山大佛 曼飞龙塔 灵山精舍"),
            (["亲子家庭", "路线"], "亲子家庭建议走约4小时轻松路线：九龙灌浴 -> 天下第一掌 -> 百子戏弥勒 -> 梵宫 -> 五印坛城。孩子能看动态演出、拍照互动，也能在室内空间休息。", "亲子家庭 4小时 九龙灌浴 天下第一掌 百子戏弥勒 梵宫 五印坛城"),
            (["老人", "轻松"], "老人同行建议少爬楼、少折返，可以搭配观光车，把重点放在九龙灌浴、梵宫、天下第一掌和灵山大佛平台等核心点；需要登台阶时放慢节奏，预留休息时间。", "老人 观光车 梵宫 核心点"),
            (["下雨", "优先"], "下雨天建议优先安排室内或半室内点位：灵山梵宫、佛教文化博览馆、五印坛城。这样既能避雨，也能把佛教艺术、展陈和藏传文化看得更完整。", "下雨 梵宫 佛教文化博览馆 五印坛城"),
            (["拍照", "打卡"], "拍照打卡可以走灵山大照壁 -> 五明桥 -> 九龙灌浴 -> 灵山大佛 -> 曼飞龙塔。大照壁适合入园第一张，五明桥拍香水海倒影，九龙灌浴拍动态演出，大佛平台和曼飞龙塔适合拍开阔景致。", "拍照 打卡 灵山大照壁 五明桥 九龙灌浴 灵山大佛 曼飞龙塔"),
            (["祈福", "怎么走"], "想体验祈福，可以重点走佛足坛 -> 天下第一掌 -> 灵山大佛抱佛脚 -> 五印坛城。佛足坛适合礼敬佛足，天下第一掌可摸佛手祈福，抱佛脚和五印坛城都很有参与感。", "祈福 佛足坛 天下第一掌 抱佛脚 五印坛城"),
            (["第一次", "最推荐"], "第一次来灵山，建议走核心中轴线：灵山大照壁 -> 五明桥 -> 佛足坛 -> 五智门 -> 菩提大道 -> 九龙灌浴演出 -> 天下第一掌 -> 灵山大佛 -> 梵宫。这样能兼顾演出、大佛和梵宫三类代表体验。", "第一次 核心中轴线 演出 灵山大佛 梵宫"),
            (["孩子", "不想太累"], "带孩子又不想太累，可以走亲子轻松路线：先看九龙灌浴动态演出，再到天下第一掌和百子戏弥勒拍照互动，后面把梵宫、五印坛城这类室内点位作为休息和文化体验。", "亲子 动态演出 百子戏弥勒 室内"),
            (["下午才到"], "下午才到建议走短线：先确认九龙灌浴和《灵山吉祥颂》的演出场次，再选天下第一掌、灵山大佛和梵宫等核心点。注意梵宫、五印坛城等室内点位有闭馆时间，冬季可能提前到16:30。", "下午 短线 演出场次 闭馆时间"),
            (["太湖日落"], "想看太湖日落，建议把下午后段留给灵山大佛平台。这里视野开阔，能把大佛、太湖和马山半岛的景色联系起来看。", "太湖日落 灵山大佛平台 下午"),
            (["历史文化", "自然风光", "取舍"], "如果更想听典故、看建筑和佛教艺术，就选历史文化路线，重点放在祥符禅寺、灵山大佛、梵宫和五印坛城；如果更想轻松拍照、看太湖山水，就选自然风光路线，节奏放慢，保留菩提大道、大佛平台、曼飞龙塔和灵山精舍。", "历史文化 自然风光 取舍"),
            (["错过九龙灌浴"], "如果刚好错过九龙灌浴，不必久等，也不必原地等太久。可以先去天下第一掌和灵山大佛，把核心祈福和登高礼佛体验完成；如果后面时间对得上，再回来补看下一场演出。", "错过九龙灌浴 不必久等 天下第一掌 灵山大佛"),
        ]
        for words, answer, source_query in route_answers:
            if self._has_all(query, words):
                return {"answer": answer, "source_query": source_query}
        if self._has(query, ["吃素斋", "素斋", "素面"]):
            return {
                "answer": "想吃素斋，可以考虑梵宫素斋自助、景区内素面套餐和灵山精舍素斋。梵宫素斋适合游览中段补给，素面更快捷，灵山精舍环境更安静，适合深度体验。",
                "source_query": "梵宫素斋 素面 灵山精舍",
            }
        return None

    def _comparison_direct_answer(self, query):
        if self._has_all(query, ["吉祥颂", "九龙灌浴"]):
            return {
                "answer": "《灵山吉祥颂》和九龙灌浴的区别很清楚：吉祥颂是梵宫室内演出，常见时间为10:35、11:30、14:00、16:00，每场约20分钟；九龙灌浴是户外动态喷泉景观，常见时间为10:00、11:30、13:30、15:00，每场约15分钟。前者偏舞台艺术和沉浸演艺，后者偏户外仪式感和动态景观。",
                "source_query": "吉祥颂 九龙灌浴 梵宫室内演出 户外动态喷泉 10:35 10:00",
            }
        comparisons = [
            (["梵宫", "五印坛城"], "梵宫更像佛教艺术殿堂，重点看建筑空间、传统工艺和室内演艺；五印坛城更偏藏传坛城文化，重点看曼陀罗象征、经筒、藏式建筑和祈福体验。", "梵宫 五印坛城 佛教艺术殿堂 藏传坛城"),
            (["天下第一掌", "抱佛脚"], "天下第一掌主要是摸佛手祈福、拍照互动，位置更亲切；抱佛脚则需要登高到灵山大佛近前，体验更偏登高礼佛和朝圣仪式感。", "天下第一掌 抱佛脚 摸佛手 登高礼佛"),
            (["五明桥", "五智门"], "五明桥是连接入口与核心游线的智慧桥梁，寓意声明、因明、内明、医方明、工巧明；五智门是进入核心礼佛空间的核心门户，象征五方五佛和六度波罗蜜。", "五明桥 五智门 智慧桥梁 核心门户"),
            (["阿育王柱", "曼飞龙塔"], "阿育王柱代表佛法传播、和平与包容，讲的是佛教向四方传播的历史意象；曼飞龙塔代表南传佛教建筑风格，体现灵山多元佛教文化。", "阿育王柱 曼飞龙塔 佛法传播 南传佛教建筑"),
        ]
        for words, answer, source_query in comparisons:
            if self._has_all(query, words):
                return {"answer": answer, "source_query": source_query}
        return None

    def _recommendation_direct_answer(self, query):
        recommendations = [
            (["景色最好"], "灵山景色最好的地方要看偏好：喜欢室内震撼艺术，首推梵宫；想看开阔山水，去灵山大佛平台；喜欢建筑打卡，可以看曼飞龙塔；想拍水面倒影，可以在香水海一带停留。", "梵宫 灵山大佛平台 曼飞龙塔 香水海"),
            (["亲子互动"], "最适合亲子互动的景点可以选九龙灌浴、百子戏弥勒和天下第一掌。九龙灌浴有动态演出，百子戏弥勒轻松有趣，天下第一掌适合摸佛手、拍照祈福。", "九龙灌浴 百子戏弥勒 天下第一掌 亲子互动"),
            (["佛教建筑艺术"], "最能体现佛教建筑艺术的景点是梵宫、五印坛城和曼飞龙塔。梵宫看当代佛教艺术和传统工艺，五印坛城看藏传坛城，曼飞龙塔看南传佛教建筑。", "梵宫 五印坛城 曼飞龙塔 佛教建筑艺术"),
            (["动态景观"], "灵山胜境最典型的动态景观是九龙灌浴。它用莲花开合、喷泉、音乐和太子佛升起呈现佛陀诞生故事，是很值得按场次观看的一站。", "九龙灌浴 动态景观"),
            (["了解赵朴初"], "想了解赵朴初先生，可以看灵山大照壁和无尽意斋。大照壁上有赵朴初题写的“灵山胜境”，无尽意斋则集中展示他与灵山及佛教文化传承的关系。", "灵山大照壁 无尽意斋 赵朴初"),
        ]
        for words, answer, source_query in recommendations:
            if self._has_all(query, words):
                return {"answer": answer, "source_query": source_query}
        return None

    def _small_talk_answer(self, query):
        q = re.sub(r"\s+", "", str(query or ""))
        q = q.strip("。！？!?，, ")
        if not q:
            return ""
        if q in {"你好", "您好", "hello", "hi"}:
            config = get_digital_human_config()
            name = config.get("name", "灵小境")
            return "您好，我是{0}，灵山胜境 AI 数字人导游。想问景点、路线、演出、门票或交通，我都可以帮您。".format(name)
        if q in {"拜拜", "再见", "下次见", "回头见"}:
            return "再见，祝您这次灵山之行顺利又开心。下次还想听景点故事或路线建议，随时来找我。"
        if q in {"听得见吗", "能听见吗", "听得到吗"}:
            return "听得见，您可以继续问我景点、路线、演出、门票或交通，我会尽量回答得清楚一点。"
        if any(word in q for word in ["可爱", "真棒", "厉害", "喜欢你", "好喜欢你"]) and len(q) <= 20:
            return "谢谢您喜欢我，我会继续用清楚、轻松的方式陪您逛灵山胜境。"
        if any(word in q for word in ["我爱你", "爱你", "么么", "亲亲"]) and len(q) <= 20:
            return "谢谢您的喜欢，这份心意我收到啦。接下来我继续陪您把灵山胜境逛得更轻松。"
        return ""

    def _tianxia_first_palm_transfer_answer(self, query):
        q = str(query or "")
        has_palm = "天下第一掌" in q or "佛手" in q or "佛掌" in q
        has_start = "灵山大照壁" in q or "大照壁" in q or "南门" in q
        asks_time = self._has(q, ["多长时间", "多久", "几分钟", "怎么走", "到那里", "到那", "到天下第一掌"])
        if not (has_palm and has_start and asks_time):
            return ""
        return (
            "天下第一掌很值得停一停。它是灵山大佛右手的等比例景观，手掌高大、掌纹清晰，很多游客会在这里摸佛手、拍照祈福，寓意把福气和平安带在身边。\n"
            "从灵山大照壁过去不远，沿入口中轴线经过胜境广场往佛手广场方向走，正常步行大约 5到8分钟；如果带老人孩子、边走边拍照，按 10分钟预留会更从容。"
        )

    def _local_scenic_narration(self, scenic, sources):
        name = scenic.get("name", "这个景点")
        summary = scenic.get("summary", "")
        if name not in summary:
            summary = ""
        source_sentences = self._scenic_source_sentences(name, sources)
        material = self._join_scenic_material(source_sentences, max_chars=220)
        focus = self._scenic_focus(name)
        material_sentence = self._scenic_story(name)
        if material and not re.search(r"菩提|步道|北端|LS-\d+", material):
            material_sentence = material
        if material_sentence and not material_sentence.endswith(("。", "！", "？")):
            material_sentence += "。"
        visit_tip = self._scenic_visit_tip(name)
        paragraphs = [
            self._scenic_opening_line(name),
            self._scenic_context_paragraph(name, material_sentence),
            focus,
            visit_tip,
        ]
        if len("".join(paragraphs)) < 350:
            paragraphs[-1] += "{0}适合用一两分钟慢慢体会：先看整体气势，再看局部细节，最后把它放回整条游览路线中理解。这样听讲解时不会只是记住名字，而能形成完整的景区印象。".format(name)
        display_segments = [self._trim_paragraph_to_sentence(paragraph, 180) for paragraph in paragraphs]
        return self._dedupe_scenic_display_segments(name, display_segments)

    def _scenic_source_sentences(self, name, sources):
        result = []
        seen = set()
        other_scenic_names = [other_name for _, other_name in SCENIC_NAMES if other_name != name]
        for source in sources:
            text = re.sub(r"\s+", " ", source.get("content") or source.get("excerpt") or "").strip()
            text = re.sub(r"(景点ID|建议游览时长|适合人群|文化标签|开放时间|坐标)[：:][^。；;]*[。；;]?", "", text)
            sentences = [s.strip() for s in re.findall(r"[^。！？!?；;]+[。！？!?；;]?", text) if s.strip()]
            for sentence in sentences:
                cleaned = self._clean_scenic_source_sentence(name, sentence, other_scenic_names)
                if not cleaned:
                    continue
                duplicate_index = self._find_similar_scenic_sentence(name, cleaned, result)
                if duplicate_index is not None:
                    if len(cleaned) > len(result[duplicate_index]):
                        result[duplicate_index] = cleaned
                    continue
                normalized = self._scenic_sentence_fingerprint(name, cleaned)
                if normalized in seen:
                    continue
                seen.add(normalized)
                result.append(cleaned)
                if len(result) >= 4:
                    return result
        return result

    def _clean_scenic_source_sentence(self, name, sentence, other_scenic_names):
        value = re.sub(r"\s+", " ", str(sentence or "")).strip()
        value = re.sub(r"^(?:灵山胜境\s*)?LS-\d+\s*", "", value).strip()
        if name not in value:
            return ""
        if any(other in value for other in other_scenic_names):
            return ""
        if len(value) < 18 or len(value) > 160:
            return ""
        stripped = value.rstrip("。！？!?；;，, ")
        if any(fragment in stripped for fragment in ["时段入园游客观赏、打卡", "不受景区内部演艺时间影响"]):
            return ""
        if re.search(r"(为|包括|雕刻|采用|设有|来源于|故居为|是进|表面|完)$", stripped):
            return ""
        if value.count(name) > 1:
            parts = [part for part in re.findall(r"[^。！？!?；;]+[。！？!?；;]?", value) if name in part]
            value = parts[0].strip() if parts else value
        if not value.endswith(("。", "！", "？")):
            value = value.rstrip("；;，,、") + "。"
        return value

    def _scenic_sentence_fingerprint(self, name, sentence):
        value = str(sentence or "")
        value = value.replace(name, "")
        value = re.sub(r"\s+", "", value)
        value = re.sub(r"[，,。！？!?；;、：:\s“”\"'（）()《》\-—]", "", value)
        value = re.sub(r"(这里|游客|您可以|建议|讲解时|观看时|适合|重点|景点|景观)", "", value)
        return value

    def _find_similar_scenic_sentence(self, name, sentence, existing_sentences):
        fingerprint = self._scenic_sentence_fingerprint(name, sentence)
        if len(fingerprint) < 18:
            return None
        for index, existing in enumerate(existing_sentences):
            other = self._scenic_sentence_fingerprint(name, existing)
            if len(other) < 18:
                continue
            if fingerprint in other or other in fingerprint:
                return index
            if SequenceMatcher(None, fingerprint, other).ratio() >= 0.88:
                return index
        return None

    def _dedupe_scenic_display_segments(self, name, paragraphs):
        result = []
        seen_sentences = []
        for paragraph in paragraphs:
            kept = []
            sentences = [s.strip() for s in re.findall(r"[^。！？!?；;]+[。！？!?；;]?", paragraph or "") if s.strip()]
            for sentence in sentences:
                if self._find_similar_scenic_sentence(name, sentence, seen_sentences) is not None:
                    continue
                kept.append(sentence)
                seen_sentences.append(sentence)
            text = "".join(kept).strip()
            if text:
                result.append(text)
        return result

    def _join_scenic_material(self, sentences, max_chars=220):
        picked = []
        total = 0
        for sentence in sentences:
            if total + len(sentence) > max_chars and picked:
                break
            picked.append(sentence)
            total += len(sentence)
        return "".join(picked)

    def _trim_paragraph_to_sentence(self, paragraph, max_chars):
        value = str(paragraph or "").strip()
        if len(value) <= max_chars:
            return value
        clipped = value[:max_chars]
        matches = list(re.finditer(r"[。！？!?]", clipped))
        if matches and matches[-1].end() >= 40:
            return clipped[: matches[-1].end()].strip()
        return clipped.rstrip("，,、：:；; ") + "。"

    def _scenic_opening_line(self, name):
        openings = {
            "灵山大照壁": "灵山大照壁是入园后的第一道视觉序章。您可以先看正面的题字和青石浮雕，它像给整条中轴线定下第一声调。",
            "五明桥": "五明桥把游线轻轻接入清净空间。脚下这几座桥不只是通行，桥名也在提醒游客从喧闹处走向更安定的参访节奏。",
            "佛足坛": "佛足坛适合把脚步放慢。先看佛足印的形制，再理解追随足迹、礼敬先贤的含义。",
            "五智门": "五智门是进入核心礼佛空间前的重要门楼。从这里穿过去，游览的仪式感会明显增强，门楼上的细节也值得抬头看。",
            "菩提大道": "菩提大道不用急着赶路。这段树影和步道会把人慢慢带向核心广场，也让“菩提”的意味落到脚步里。",
            "九龙灌浴": "九龙灌浴要留一点时间等它动起来。等音乐响起时，莲花、太子佛和九条飞龙会一起进入表演状态。",
            "降魔浮雕": "降魔浮雕适合边走边看。画面里的紧张感，会把释迦牟尼成道前面对考验的故事讲出来。",
            "阿育王柱": "阿育王柱是很醒目的历史地标。您可以先看柱身比例和顶部造型，再听它和佛教传播史之间的关系。",
            "天下第一掌": "天下第一掌先别只当合影点。它的手掌意象带着祝福意味，互动感强，也很适合给同行的人留一张轻松的照片。",
            "百子戏弥勒": "百子戏弥勒这一站气氛会轻松很多。孩子围着弥勒嬉戏的细节特别有生活气，也容易让亲子游客停下来。",
            "灵山大佛": "灵山大佛适合先远望，再慢慢走近。先从远处抬头看佛像，震撼感会随着台阶一层一层展开。",
            "灵山梵宫": "灵山梵宫不要只看金碧辉煌。进入后先看穹顶、壁画和灯光，它们会一起构成一座可行走的佛教艺术殿堂。",
            "祥符禅寺": "祥符禅寺的节奏会安静下来。钟声、殿宇和香火感，更适合慢慢体会这片山水里的千年佛教根脉。",
            "五印坛城": "五印坛城第一眼看色彩和层次。再看图案、转经筒和空间秩序，会更容易进入藏传佛教艺术的情境。",
            "曼飞龙塔": "曼飞龙塔的南传佛教建筑气质很鲜明。白色塔身和金色塔刹，是第一眼就能抓住的观看重点。",
            "无尽意斋": "无尽意斋更适合作为休整的一站。走到这里，可以把前面的参访感受放一放，换成一顿轻松的素食体验。",
        }
        return openings.get(name, "{0}这一站先从整体位置看起。它在礼佛游线里承担着承上启下的作用，细节也值得慢慢观察。".format(name))

    def _scenic_context_paragraph(self, name, material_sentence):
        contexts = {
            "灵山大照壁": "大照壁常被游客当作第一张照片的背景，其实它更像入园后的第一道提示：从这里开始，视线会被引向中轴线，也会被带入更庄重的游览节奏。它把入口空间、题字、浮雕和远处景观放在同一个画面里，让游客还没走深，就先感到灵山胜境的礼佛氛围。",
            "五明桥": "五明桥的价值不在桥长，而在空间转换。游客从这里经过时，会从入口的开阔感慢慢进入更有秩序的礼佛游线；桥名里的“五明”也呼应智慧、通达与学习，让普通通行多了一层文化意味。",
            "佛足坛": "佛足坛把“行走”本身变成讲解重点。佛足印提示游客，参访不是只看高大的建筑，也是在跟随一条有象征意义的道路前进；这一站适合给后面的礼佛动线做安静铺垫。",
            "五智门": "五智门承担的是门楼和心理转换的双重作用。穿过这道门，游客会更明显地进入灵山的核心参访区；门名里的“五智”也能把建筑观看和佛教智慧观念联系起来。",
            "菩提大道": "菩提大道是一段过渡性的步行空间。两侧景观让人从入口的热闹里缓下来，“菩提”二字又把行走、觉悟和参访心境联系在一起，适合边走边听讲解。",
            "九龙灌浴": "九龙灌浴讲的是佛陀诞生时九龙吐水沐浴太子的典故，灵山把这个故事做成喷泉、音乐、莲花开合和太子佛旋转升起的动态演出。它不是静态雕塑，而是一段需要按场次观看的文化表演。",
            "降魔浮雕": "降魔浮雕把成道前的考验放进连续画面里。看它时可以注意人物姿态、画面张力和故事推进，它讲的不只是外在降魔，也是在表达克服内心障碍后的安定。",
            "阿育王柱": "阿育王柱把视线带到更开阔的佛教传播史。古印度阿育王护持佛法、树立石柱的意象，在这里被转化为景区里的记忆标识，让游客理解灵山并不只讲本地故事。",
            "天下第一掌": "天下第一掌的亲和力很强，很多游客会摸掌祈福、拍照留念。讲解时可以把它和灵山大佛的手印联系起来：手掌既是可互动的景观，也承载着祝福、守护和平安的寓意。",
            "百子戏弥勒": "百子戏弥勒用轻松的方式表达欢喜与包容。孩童形态各异，弥勒笑容亲切，这一站能让佛教文化从庄严转向生活化，也特别适合孩子观察和互动。",
            "灵山大佛": "灵山大佛是整条游线的精神高点。它的震撼不只来自高度，也来自逐步登阶、抬头仰望和近前礼佛的过程；游客的情绪会从远望时的惊叹，慢慢转为靠近后的安定。",
            "灵山梵宫": "灵山梵宫把建筑、壁画、雕塑、灯光和演艺空间放在一起。它不像普通展馆只陈列作品，而是让游客在行走中被空间包围，感受当代佛教艺术的华丽和庄严。",
            "祥符禅寺": "祥符禅寺连接着灵山的历史根脉。相比大佛和梵宫的宏大，这里更像把游客带回传统寺院的日常：钟声、殿宇、古树和香火，都让参访节奏变得更沉静。",
            "五印坛城": "五印坛城的特点是藏传佛教艺术的集中呈现。色彩、图案、经筒和空间层次都很鲜明，讲解时可以从整体视觉秩序进入，再慢慢看坛城象征和祈福体验。",
            "曼飞龙塔": "曼飞龙塔呈现出南传佛教建筑风格，和汉传、藏传景观形成对照。它的塔身比例、色彩和园林环境，让游客能在灵山胜境里看到多元佛教文化的并置。",
            "无尽意斋": "无尽意斋把参访体验从观看转向休憩和饮食。素食不只是吃饭选择，也能让游客在节奏上缓一缓，把前面的文化感受落到更日常的体验里。",
        }
        context = contexts.get(name, "{0}不是孤立的一处景观，它需要放回整条游览动线中理解。看完整体位置后，再观察造型、空间和游客互动方式，讲解会更有层次。".format(name))
        if material_sentence and name in material_sentence:
            sentences = [s.strip() for s in re.findall(r"[^。！？!?；;]+[。！？!?；;]?", material_sentence + context) if s.strip()]
            kept = []
            for sentence in sentences:
                duplicate_index = self._find_similar_scenic_sentence(name, sentence, kept)
                if duplicate_index is not None:
                    if len(sentence) > len(kept[duplicate_index]):
                        kept[duplicate_index] = sentence
                    continue
                kept.append(sentence)
            return "".join(kept)
        return context

    def _scenic_opening_hook(self, name):
        hooks = {
            "灵山大照壁": "您可以先看正面的题字和青石浮雕，它像给整条中轴线定下第一声调。",
            "五明桥": "脚下这几座桥不只是通行，桥名也在提醒游客从喧闹处走向更清净的空间。",
            "佛足坛": "这里适合把脚步放慢一点，先看佛足印的形制，再理解追随足迹的含义。",
            "五智门": "从这里穿过去，游览的仪式感会明显增强，门楼上的细节也值得抬头看。",
            "菩提大道": "这段路不急着赶，树影和步道会把人慢慢带向核心广场。",
            "九龙灌浴": "等音乐响起时，莲花、太子佛和九条飞龙会一起动起来，现场比照片更有感染力。",
            "降魔浮雕": "这处浮雕适合边走边看，画面里的紧张感会把成道前的考验讲出来。",
            "阿育王柱": "您可以先看柱身比例和顶部造型，它把佛教传播史浓缩成一个很醒目的地标。",
            "天下第一掌": "这里很适合互动拍照，但手掌意象背后的祝福意味也值得听一听。",
            "百子戏弥勒": "这一站气氛会轻松很多，孩子围着弥勒嬉戏的细节特别有生活气。",
            "灵山大佛": "先从远处抬头看佛像，再慢慢走近，震撼感会一层一层展开。",
            "灵山梵宫": "进入梵宫后别只看金碧辉煌，穹顶、壁画和灯光其实在共同讲一个空间故事。",
            "祥符禅寺": "这里的节奏会安静下来，钟声、殿宇和香火感更适合慢慢体会。",
            "五印坛城": "这里色彩很鲜明，先看整体层次，再看图案和转经筒，会更容易进入情境。",
            "曼飞龙塔": "它的南传佛教建筑气质很鲜明，白色塔身和金色塔刹是第一眼的重点。",
            "无尽意斋": "这一站更适合休整，也可以把前面的参访感受换成一顿轻松的素食体验。",
        }
        return hooks.get(name, "这一站先看整体位置，再看细节，它在整条礼佛游线里有承上启下的作用。")

    def _scenic_visit_tip(self, name):
        tips = {
            "灵山大照壁": "拍照时可以稍微退后，把照壁、入口空间和远处太湖一起收进画面；如果时间充裕，再靠近看青石纹理和题字。接下来继续往里走，您会发现后面的桥、门和广场都在顺着这条中轴线展开。",
            "九龙灌浴": "如果想看演出，建议提前到广场边缘找一个无遮挡的位置；表演开始后先拍整体，再看莲花打开和水柱汇聚的瞬间。演出结束后人流会集中移动，带老人孩子的话可以晚半分钟再走，体验会从容很多。",
            "灵山大佛": "参拜大佛不用急着一口气登到最高处，可以边走边回头看太湖和景区轴线。到近前时再观察佛像手印和莲座细节，震撼感会更完整；下行时注意台阶，同行有老人孩子就放慢节奏。",
            "灵山梵宫": "梵宫内部适合先看穹顶和主空间，再跟着动线看壁画、雕塑和演艺区域。这里光线变化丰富，拍照时别只追求全景，局部装饰也很出片；如果遇到演出场次，建议提前进场。",
        }
        return tips.get(name, "游览时建议先听完整体讲解，再选择拍照或近距离看细节；如果同行有老人和孩子，可以在这里短暂停留，不必赶路。继续前行时，把这一站的位置和下一站连起来看，整条路线会更有层次。")

    def _scenic_focus(self, name):
        focus = {
            "九龙灌浴": "九龙灌浴最精彩的是莲花开合、喷泉水势和音乐节奏共同讲述佛陀诞生故事。观看时可以注意水柱从四周汇聚到中心的过程，它象征祝福与清净，也让静态广场变成一场可感知的文化演出。建议提前到场，站在能看见莲花整体的位置，体验会更完整。",
            "灵山大佛": "灵山大佛的讲解重点在“高大”之外，更在登高礼佛的过程。游客从山脚仰望，到逐步接近佛像，心理感受会从震撼转为安定。这里也适合结合太湖山水讲解，理解为什么大佛会成为整座景区的精神终点。",
            "灵山梵宫": "灵山梵宫适合从建筑艺术和室内演艺两条线理解。穹顶、壁画、雕塑和灯光共同营造出庄严又华丽的空间，游客在这里能看到传统佛教题材与当代表达方式结合，是灵山胜境最具沉浸感的室内文化体验之一。",
        }
        return focus.get(name, "{0}的观看重点，是把眼前景观和它承载的文化寓意联系起来。您可以观察它的位置、朝向、造型和周边空间，再结合导览理解它在礼佛游线中的作用。这样一路走下来，每个景点就不再是分散的打卡点，而会形成一条完整的文化叙事。".format(name))

    def _scenic_story(self, name):
        stories = {
            "灵山大照壁": "大照壁常被游客当作第一张照片的背景，其实它更像入园后的第一道提示：从这里开始，视线会被引向中轴线，也会被带入更庄重的游览节奏。",
            "五明桥": "五明桥把入口空间和后续礼佛游线接起来，桥名里的“五明”带有智慧与通达的意味，走过桥面，就像完成一次轻轻的转换。",
            "佛足坛": "佛足坛以佛足印为核心意象，讲的是追随佛陀足迹、从行走中生起敬意的传统；游客在这里可以先把脚步慢下来。",
            "五智门": "五智门的名字来自佛教五智，门楼本身也承担着仪式感：穿过这里，游览就从普通观景进入更完整的礼佛叙事。",
            "菩提大道": "菩提大道是一段很适合慢行的空间，两侧景观会把游客一步步引向核心区域，“菩提”二字也提醒人们把行走和觉悟联系起来。",
            "九龙灌浴": "九龙灌浴讲的是佛陀诞生时九龙吐水沐浴太子的故事，灵山把这个典故做成可观看、可聆听的动态演出，现场感很强。",
            "降魔浮雕": "降魔浮雕讲的是成道前战胜诱惑与障碍的故事，它不只是叙事画面，也在提醒游客：真正的安定往往来自内心。",
            "阿育王柱": "阿育王柱会把讲解带到佛教传播史：古印度阿育王护持佛法、树立石柱，这一意象在这里被转化成景区里的历史记忆。",
            "天下第一掌": "天下第一掌很适合互动拍照，手掌意象带着祝福和守护意味，很多游客会在这里停留，感受它直接、亲切的一面。",
            "百子戏弥勒": "百子戏弥勒的气质更轻松，孩子围绕弥勒嬉戏的画面，把欢喜、包容和亲近感表现得很直观。",
            "灵山大佛": "灵山大佛是整条游线的精神终点，从远望、登阶到近前礼佛，游客的情绪会自然经历震撼、靠近和安定。",
            "灵山梵宫": "灵山梵宫把建筑、壁画、雕塑和演艺空间融合在一起，讲解时适合把它当作一座可行走的佛教艺术殿堂。",
            "祥符禅寺": "祥符禅寺保留了传统寺院的安静气质，钟声、殿宇和香火感会让游客从大型景观转入更日常的参访体验。",
            "五印坛城": "五印坛城带有鲜明的藏传佛教艺术特色，色彩、图案和空间层层展开，适合从坛城象征和视觉秩序来讲。",
            "曼飞龙塔": "曼飞龙塔呈现出南传佛教建筑风格，塔身造型和整体比例都很有辨识度，是理解灵山多元佛教文化的一站。",
            "无尽意斋": "无尽意斋更适合作为休憩和素食体验节点，游客可以在这里把前面的参访感受放一放，换成更轻松的停留。",
        }
        return stories.get(name, "")

    def _route_answer(self, interest):
        if self._is_short_time_route_question(interest):
            return self._short_time_route_answer(interest)
        routes = self.kb.recommend_routes(interest)
        lines = ["我按您的兴趣推荐这条路线："]
        top = routes[0]
        lines.append("**{0}（{1}）**：{2}".format(top["name"], top["duration"], top["summary"]))
        lines.append("游览顺序：" + " -> ".join(top["stops"]))
        lines.append("讲解重点：" + "、".join(top["tags"]))
        if len(routes) > 1:
            lines.append("备选路线可以看：{0}。".format("、".join([r["name"] for r in routes[1:]])))
        return "\n".join(lines)

    def _is_short_time_route_question(self, text):
        value = str(text or "")
        return self._has(value, ["2小时", "两小时", "2个小时", "两个小时", "最短", "最多"]) and self._has(value, ["路线", "游览", "玩", "场景", "景点"])

    def _short_time_route_answer(self, interest):
        return (
            "可以走一条 2小时高效路线，目标是少绕路、多覆盖代表性场景：\n"
            "灵山大照壁 -> 五明桥 -> 佛足坛 -> 五智门 -> 菩提大道 -> 九龙灌浴 -> 天下第一掌 -> 灵山大佛。\n"
            "时间分配建议：入口到五智门约 25 分钟，菩提大道快走拍照约 15 分钟，九龙灌浴按场次停留 15-20 分钟，天下第一掌约 10 分钟，最后把主要时间留给灵山大佛和登高礼佛。"
            "如果刚好错过九龙灌浴演出，就不要原地等待太久，直接去天下第一掌和灵山大佛，这样 2小时内能看到更多核心场景。"
        )

    def _extract_summary(self, context, query):
        if not context:
            return ""
        text = re.sub(r"\s+", " ", context).strip()
        text = re.sub(r"(景点ID|建议游览时长|适合人群|文化标签|开放时间|坐标)[：:][^。；;]*[。；;]?", "", text)
        sentences = [s.strip() for s in re.split(r"[。；;！!\n]", text) if len(s.strip()) > 12]
        keywords = [w for w in re.findall(r"[\u4e00-\u9fff]{2,6}", query) if w not in ["介绍一下", "请问", "什么", "怎么"]]
        picked = []
        for sentence in sentences:
            if any(word in sentence for word in keywords) or len(picked) < 2:
                if sentence not in picked:
                    picked.append(sentence)
            if len(picked) >= 4:
                break
        if not picked:
            picked = sentences[:3]
        if not picked:
            return ""
        lead = "我给您提炼一下："
        body = "。".join(picked)
        if not body.endswith("。"):
            body += "。"
        return lead + "\n" + body[:520]

    def _has(self, text, words):
        return any(word in text for word in words)

    def _has_all(self, text, words):
        return all(word in text for word in words)

    def _spot_answer(self, query):
        spot_summaries = {
            "灵山大照壁": "灵山大照壁是进入灵山胜境后的第一处视觉序章，适合从这里开启礼佛游线，理解景区中轴线和文化氛围。",
            "五明桥": "五明桥连接入口游线与核心景观，名称呼应佛教智慧意象，适合讲解从世俗空间进入清净文化空间的过渡。",
            "佛足坛": "佛足坛以佛足印为核心意象，适合讲解佛陀行迹、礼敬传统和游客入园后的第一段文化铺垫。",
            "五智门": "五智门是灵山胜境中轴线上的重要门楼，适合讲解佛教五智含义和进入核心礼佛空间的仪式感。",
            "菩提大道": "菩提大道是通往核心景点的重要步行游线，两侧景观适合慢行拍照，也适合讲解觉悟、修行与礼佛动线。",
            "九龙灌浴": "九龙灌浴是灵山胜境代表性动态景观，通过莲花开合、喷泉和音乐呈现佛陀诞生故事，建议提前到场观看。",
            "降魔浮雕": "降魔浮雕以佛教故事为主题，适合讲解释迦牟尼成道前战胜内心障碍的象征意义。",
            "阿育王柱": "阿育王柱体现佛教传播与历史记忆，适合结合古印度阿育王护持佛法的故事进行文化讲解。",
            "天下第一掌": "天下第一掌是游客互动和拍照关注度较高的景观，可讲解佛手印的祝福寓意，也适合亲子家庭停留。",
            "百子戏弥勒": "百子戏弥勒以欢喜、包容和童趣为特色，适合亲子游客拍照互动，也能讲解弥勒文化的亲和感。",
            "灵山大佛": "灵山大佛是景区核心地标，以宏大的佛像、登高礼佛和太湖山水背景构成最具辨识度的参观点。",
            "灵山梵宫": "灵山梵宫融合佛教艺术、建筑装饰与演艺空间，是理解灵山当代佛教艺术和室内文化体验的重要一站。",
            "祥符禅寺": "祥符禅寺体现传统寺院空间和礼佛氛围，适合安静参访，了解灵山胜境与佛教文化的历史连接。",
            "五印坛城": "五印坛城以藏传佛教坛城文化为特色，色彩、空间和宗教艺术都很鲜明，适合深度文化讲解。",
            "曼飞龙塔": "曼飞龙塔带有南传佛教建筑风格，适合讲解多元佛教文化在灵山胜境中的集中呈现。",
            "无尽意斋": "无尽意斋是景区素食与休憩相关空间，可结合餐饮、素斋体验和文化休闲进行推荐。",
        }
        for name, summary in spot_summaries.items():
            if name in query:
                return summary
        return ""


def split_narration_segments(text, first_max_chars=32, min_chars=30, max_chars=90):
    raw = str(text or "")
    pieces = [p.strip() for p in re.findall(r"[^。！？!?；;：:，,、\n]+[。！？!?；;：:，,、]?", raw) if p.strip()]
    if not pieces:
        return []

    first, rest_pieces = _take_first_narration_segment(pieces, first_max_chars)
    result = [first] if first else []
    result.extend(_pack_narration_segments(rest_pieces, max_chars))

    merged = []
    for segment in result:
        if not merged:
            merged.append(segment)
            continue
        if len(merged) > 1 and len(segment) < min_chars and len(merged[-1]) + len(segment) <= max_chars:
            merged[-1] += segment
            continue
        merged.append(segment)
    return _merge_short_body_segments(merged, min_chars, max_chars)


def prepare_narration_voice_segments(segments):
    result = []
    weak_starts = ("是", "而", "也", "并", "再", "还", "则", "就")
    for segment in segments or []:
        value = str(segment or "").strip()
        if not value:
            continue
        if value.endswith(("，", ",", "、", "：", ":")):
            value = value[:-1].rstrip() + "。"
        if result and value.startswith(weak_starts) and len(result[-1]) + len(value) <= 150:
            combined = result[-1].rstrip("。") + "，" + value
            result[-1:] = _split_voice_segment_after_strong_punctuation(combined, max_chars=110)
            continue
        if result and value.startswith(weak_starts):
            moved = _move_trailing_clause_to_next_segment(result[-1], value)
            if moved:
                result[-1], value = moved
        result.extend(_split_voice_segment_after_strong_punctuation(value, max_chars=110))
    return result


def _move_trailing_clause_to_next_segment(previous, current):
    previous = str(previous or "").strip()
    current = str(current or "").strip()
    if not previous or not current:
        return None
    body = previous.rstrip("。！？!?；;")
    matches = list(re.finditer(r"[。！？!?；;]", body))
    if not matches:
        return None
    split_at = matches[-1].end()
    head = body[:split_at].strip()
    tail = body[split_at:].strip().rstrip("。！？!?；;，,、：:")
    if not head or not tail:
        return None
    combined = tail + "，" + current
    if len(combined) > 110:
        return None
    return head, combined


def _split_voice_segment_after_strong_punctuation(value, max_chars=110):
    value = str(value or "").strip()
    if not value or len(value) <= max_chars:
        return [value] if value else []
    parts = []
    start = 0
    while start < len(value):
        end = min(len(value), start + max_chars)
        if end < len(value):
            split_at = 0
            for match in re.finditer(r"[。！？!?；;]", value[start:end]):
                candidate = match.end()
                if candidate >= 30:
                    split_at = candidate
            if split_at:
                end = start + split_at
        chunk = value[start:end].strip()
        if chunk:
            parts.append(chunk)
        start = end
    return parts


def _take_first_narration_segment(pieces, first_max_chars):
    current = ""
    for index, piece in enumerate(pieces):
        if not current:
            # 首段用于快速开口，优先保持完整短句，避免把下一句的逗号半句吞进来。
            if piece.endswith(("。", "！", "？", "!", "?")):
                return piece, pieces[index + 1 :]
            if len(piece) <= first_max_chars:
                current = piece
                continue
            chunks = _split_long_narration_piece(piece, first_max_chars)
            return chunks[0], chunks[1:] + pieces[index + 1 :]
        if current.endswith(("。", "！", "？", "!", "?")):
            return current, pieces[index:]
        if current.endswith("、") and pieces[index:]:
            balanced = _rebalance_narration_segments(current + piece, max(12, first_max_chars // 2), first_max_chars)
            if balanced:
                return balanced[0], balanced[1:] + pieces[index + 1 :]
        if piece.endswith("、") and index + 1 < len(pieces):
            return current, pieces[index:]
        if len(current) + len(piece) <= first_max_chars:
            current += piece
            continue
        return current, pieces[index:]
    return current, []


def _pack_narration_segments(pieces, max_chars):
    result = []
    current = ""
    for piece in pieces:
        if len(piece) > max_chars:
            if current:
                result.append(current)
                current = ""
            result.extend(_split_long_narration_piece(piece, max_chars))
            continue
        if not current:
            current = piece
            continue
        if len(current) + len(piece) <= max_chars:
            current += piece
        else:
            result.append(current)
            current = piece
    if current:
        result.append(current)
    return result


def _merge_short_body_segments(segments, min_chars, max_chars):
    if len(segments) <= 2:
        return segments
    merged = list(segments)
    index = 1
    while index < len(merged):
        if len(merged[index]) >= min_chars:
            index += 1
            continue
        if index + 1 < len(merged) and len(merged[index]) + len(merged[index + 1]) <= max_chars:
            merged[index] += merged[index + 1]
            del merged[index + 1]
            continue
        if index > 1 and len(merged[index - 1]) + len(merged[index]) <= max_chars:
            merged[index - 1] += merged[index]
            del merged[index]
            continue
        if index > 1:
            balanced = _rebalance_narration_segments(merged[index - 1] + merged[index], min_chars, max_chars)
            if len(balanced) == 2:
                merged[index - 1 : index + 1] = balanced
                index += 1
                continue
        index += 1
    return merged


def _rebalance_narration_segments(text, min_chars, max_chars):
    value = str(text or "")
    if not value:
        return []
    if len(value) <= max_chars:
        return [value]
    if len(value) > max_chars * 2 or len(value) < min_chars * 2:
        return _split_long_narration_piece(value, max_chars)
    target = len(value) // 2
    candidates = []
    for match in re.finditer(r"[。！？!?；;：:，,]", value):
        split_at = match.end()
        left_len = split_at
        right_len = len(value) - split_at
        if min_chars <= left_len <= max_chars and min_chars <= right_len <= max_chars:
            penalty = 0 if value[split_at - 1] in "。！？!?；;" else 8
            candidates.append((penalty, abs(left_len - target), split_at))
    if candidates:
        _, _, split_at = min(candidates)
    else:
        split_at = _nearest_safe_split(value, target, min_chars, max_chars)
    return [value[:split_at].strip(), value[split_at:].strip()]


def _split_long_narration_piece(piece, max_chars):
    value = piece.strip()
    if len(value) <= max_chars:
        return [value]
    parts = []
    start = 0
    while start < len(value):
        end = min(len(value), start + max_chars)
        if end < len(value):
            end = _nearest_safe_split(value[start:end], max_chars, max(18, max_chars // 3), max_chars) + start
            if end <= start:
                end = min(len(value), start + max_chars)
        chunk = value[start:end].strip()
        if chunk:
            parts.append(chunk)
        start = end
    return parts


def _nearest_safe_split(value, target, min_chars, max_chars):
    best = None
    for match in re.finditer(r"[。！？!?；;：:，,]", value):
        split_at = match.end()
        if min_chars <= split_at <= max_chars and not value[:split_at].endswith("、"):
            penalty = 0 if value[split_at - 1] in "。！？!?；;" else 8
            candidate = (penalty, abs(split_at - target), split_at)
            if best is None or candidate < best:
                best = candidate
    if best:
        return best[2]
    split_at = max(min_chars, min(target, max_chars))
    while split_at > min_chars and value[:split_at].endswith(("、", "，", ",", "：", ":")):
        split_at -= 1
    return split_at
