import json
from pathlib import Path


TEMPLATES = {
    "kling_o1_i2v": {
        "name": "可灵图生视频",
        "description": "可灵 O1 模型 · 1080p · 单图生视频",
        "data": {
            "nodes": [
                {
                    "id": "image_node_1",
                    "type": "image",
                    "title": "图片上传",
                    "pos": {"x": 80, "y": 200},
                    "data": {}
                },
                {
                    "id": "kling_node_1",
                    "type": "kling_api",
                    "title": "可灵生视频",
                    "pos": {"x": 380, "y": 150},
                    "data": {
                        "prompt": "",
                        "model": "kling-video-o1",
                        "duration": "5s",
                        "resolution": "1080p",
                        "generation_mode": "image_to_video",
                        "cfg_scale": 50
                    }
                },
                {
                    "id": "output_node_1",
                    "type": "output",
                    "title": "视频输出",
                    "pos": {"x": 700, "y": 200},
                    "data": {"output_name": "kling_output"}
                }
            ],
            "edges": [
                {
                    "start_node": "image_node_1",
                    "start_socket": 0,
                    "end_node": "kling_node_1",
                    "end_socket": 0
                },
                {
                    "start_node": "kling_node_1",
                    "start_socket": 0,
                    "end_node": "output_node_1",
                    "end_socket": 0
                }
            ]
        }
    },
    "kling_o1_first_last": {
        "name": "可灵首尾帧",
        "description": "可灵 O1 模型 · 1080p · 首尾帧生视频",
        "data": {
            "nodes": [
                {
                    "id": "image_node_1",
                    "type": "image",
                    "title": "首帧图片",
                    "pos": {"x": 80, "y": 130},
                    "data": {}
                },
                {
                    "id": "image_node_2",
                    "type": "image",
                    "title": "尾帧图片",
                    "pos": {"x": 80, "y": 320},
                    "data": {}
                },
                {
                    "id": "kling_node_1",
                    "type": "kling_api",
                    "title": "可灵生视频",
                    "pos": {"x": 380, "y": 175},
                    "data": {
                        "prompt": "",
                        "model": "kling-video-o1",
                        "duration": "5s",
                        "resolution": "1080p",
                        "generation_mode": "first_last_frame",
                        "cfg_scale": 50
                    }
                },
                {
                    "id": "output_node_1",
                    "type": "output",
                    "title": "视频输出",
                    "pos": {"x": 700, "y": 225},
                    "data": {"output_name": "kling_output"}
                }
            ],
            "edges": [
                {
                    "start_node": "image_node_1",
                    "start_socket": 0,
                    "end_node": "kling_node_1",
                    "end_socket": 0
                },
                {
                    "start_node": "image_node_2",
                    "start_socket": 0,
                    "end_node": "kling_node_1",
                    "end_socket": 1
                },
                {
                    "start_node": "kling_node_1",
                    "start_socket": 0,
                    "end_node": "output_node_1",
                    "end_socket": 0
                }
            ]
        }
    },
    "jimeng_v30_i2v": {
        "name": "即梦图生视频",
        "description": "即梦 v30 模型 · 720P · 单图生视频",
        "data": {
            "nodes": [
                {
                    "id": "image_node_1",
                    "type": "image",
                    "title": "图片上传",
                    "pos": {"x": 80, "y": 200},
                    "data": {}
                },
                {
                    "id": "jimeng_node_1",
                    "type": "jimeng_api",
                    "title": "即梦生视频",
                    "pos": {"x": 380, "y": 150},
                    "data": {
                        "prompt": "",
                        "model": "jimeng_v30",
                        "duration": "5s",
                        "fps": "24fps",
                        "seed": -1,
                        "generation_mode": "image_to_video",
                        "resolution": "720P"
                    }
                },
                {
                    "id": "output_node_1",
                    "type": "output",
                    "title": "视频输出",
                    "pos": {"x": 700, "y": 200},
                    "data": {"output_name": "jimeng_output"}
                }
            ],
            "edges": [
                {
                    "start_node": "image_node_1",
                    "start_socket": 0,
                    "end_node": "jimeng_node_1",
                    "end_socket": 0
                },
                {
                    "start_node": "jimeng_node_1",
                    "start_socket": 0,
                    "end_node": "output_node_1",
                    "end_socket": 0
                }
            ]
        }
    },
    "jimeng_v30_first_last": {
        "name": "即梦首尾帧",
        "description": "即梦 v30 模型 · 720P · 首尾帧生视频",
        "data": {
            "nodes": [
                {
                    "id": "image_node_1",
                    "type": "image",
                    "title": "首帧图片",
                    "pos": {"x": 80, "y": 130},
                    "data": {}
                },
                {
                    "id": "image_node_2",
                    "type": "image",
                    "title": "尾帧图片",
                    "pos": {"x": 80, "y": 320},
                    "data": {}
                },
                {
                    "id": "jimeng_node_1",
                    "type": "jimeng_api",
                    "title": "即梦生视频",
                    "pos": {"x": 380, "y": 175},
                    "data": {
                        "prompt": "",
                        "model": "jimeng_v30",
                        "duration": "5s",
                        "fps": "24fps",
                        "seed": -1,
                        "generation_mode": "first_last_frame",
                        "resolution": "720P"
                    }
                },
                {
                    "id": "output_node_1",
                    "type": "output",
                    "title": "视频输出",
                    "pos": {"x": 700, "y": 225},
                    "data": {"output_name": "jimeng_output"}
                }
            ],
            "edges": [
                {
                    "start_node": "image_node_1",
                    "start_socket": 0,
                    "end_node": "jimeng_node_1",
                    "end_socket": 0
                },
                {
                    "start_node": "image_node_2",
                    "start_socket": 0,
                    "end_node": "jimeng_node_1",
                    "end_socket": 1
                },
                {
                    "start_node": "jimeng_node_1",
                    "start_socket": 0,
                    "end_node": "output_node_1",
                    "end_socket": 0
                }
            ]
        }
    },
    "gemini_image_gen": {
        "name": "香蕉生图",
        "description": "Gemini 香蕉模型 · 参考图片生成新图片",
        "data": {
            "nodes": [
                {
                    "id": "image_node_1",
                    "type": "image",
                    "title": "参考图片",
                    "pos": {"x": 80, "y": 200},
                    "data": {}
                },
                {
                    "id": "gemini_node_1",
                    "type": "gemini_api",
                    "title": "香蕉生图",
                    "pos": {"x": 380, "y": 150},
                    "data": {
                        "prompt": "",
                        "model": "gemini-3-pro-image-preview",
                        "aspect_ratio": "16:9",
                        "resolution": "2K"
                    }
                },
                {
                    "id": "output_node_1",
                    "type": "output",
                    "title": "图片输出",
                    "pos": {"x": 700, "y": 200},
                    "data": {"output_name": "gemini_output"}
                }
            ],
            "edges": [
                {
                    "start_node": "image_node_1",
                    "start_socket": 0,
                    "end_node": "gemini_node_1",
                    "end_socket": 0
                },
                {
                    "start_node": "gemini_node_1",
                    "start_socket": 0,
                    "end_node": "output_node_1",
                    "end_socket": 0
                }
            ]
        }
    }
}


def get_template_list():
    return [
        {
            "id": key,
            "name": value["name"],
            "description": value["description"]
        }
        for key, value in TEMPLATES.items()
    ]


def get_template(template_id):
    return TEMPLATES.get(template_id)
