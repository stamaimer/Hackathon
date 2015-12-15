# -*- coding: utf-8 -*-

import json
import redis
import random
import string
import pymysql
from datetime import datetime

from gevent.pywsgi import WSGIServer

# from gevent import monkey
#
# monkey.patch_all()

from flask import Flask
from flask import jsonify
from flask import request

app = Flask(__name__)

app.debug = True

connection = pymysql.connect(host="localhost", user="root", passwd="toor", db="eleme")

cursor = connection.cursor()

redis_cli = redis.Redis(host="localhost", port=6379, db=0)

access_tokens = {}

carts = {}

orders = {}

candidates = string.lowercase + string.digits

TOKEN_LENGTH = 5


def gen_access_token(uid):

    current = datetime.now()

    access_token = ''.join(random.choice(candidates) for _ in xrange(TOKEN_LENGTH))

    access_tokens[access_token] = {"create_time": current, "ordered": 0, "uid": uid}

    return access_token


def validate_access_token(access_token):

    return (access_token in access_tokens) and \
           (datetime.now() - access_tokens[access_token]["create_time"]).total_seconds() <= 1800


def _gen_cart(access_token):

    cart_id = ''.join(random.choice(candidates) for _ in xrange(TOKEN_LENGTH))

    carts[cart_id] = {"access_token": access_token, "foods": [], "total": 0}

    return {"cart_id": cart_id}


def _gen_order(access_token, foods, amount):

    order_id = ''.join(random.choice(candidates) for _ in xrange(TOKEN_LENGTH))

    orders[access_token] = {"id": order_id, "user_id": access_tokens[access_token]["uid"], "items": foods, "total": amount}

    return {"id": order_id}


@app.errorhandler(400)
def malformed_json(error):

    response = {}

    response["code"] = "MALFORMED_JSON"

    response["message"] = "格式错误"

    return jsonify(response), 400


@app.route("/login", methods=["POST"])
def login():

    if request.method == "POST":

        response = {}

        if request.data:

            data = request.json

        else:

            response["code"] = "EMPTY_REQUEST"

            response["message"] = "请求体为空"

            return jsonify(response), 400

        username = data["username"]
        password = data["password"]

        cursor.execute("select id, password from user where name = %s", username)

        result = cursor.fetchall()

        if result and result[0][1] == password:

            response["user_id"] = result[0][0]

            response["username"] = username

            response["access_token"] = gen_access_token(result[0][0])

            return jsonify(response), 200

        else:

            response["code"] = "USER_AUTH_FAIL"

            response["message"] = "用户名或密码错误"

            return jsonify(response), 403


@app.route("/foods", methods=["GET"])
def query_foods():

    if request.method == "GET":

        response = {}

        access_token = request.args.get("access_token")

        if not access_token:

            access_token = request.headers.get("Access-Token")

        if validate_access_token(access_token):

            cursor.execute("select * from food")

            results = cursor.fetchall()

            foods = []

            for result in results:

                food = {}

                food["id"] = result[0]

                food["stock"] = result[1]

                food["price"] = result[2]

                foods.append(food)

            return json.dumps(foods), 200

        else:

            response["code"] = "INVALID_ACCESS_TOKEN"

            response["message"] = "无效的令牌"

            return jsonify(response), 401


@app.route("/carts", methods=["POST"])
def gen_cart():

    if request.method == "POST":

        response = {}

        access_token = request.args.get("access_token")

        if not access_token:

            access_token = request.headers.get("Access-Token")

        if validate_access_token(access_token):

            response = _gen_cart(access_token)

            return jsonify(response), 200

        else:

            response["code"] = "INVALID_ACCESS_TOKEN"

            response["message"] = "无效的令牌"

            return jsonify(response), 401


@app.route("/carts/<cart_id>", methods=["PATCH"])
def add_food(cart_id):

    if request.method == "PATCH":

        response = {}

        access_token = request.args.get("access_token")

        if not access_token:

            access_token = request.headers.get("Access-Token")

        if validate_access_token(access_token):

            if cart_id in carts:

                if carts[cart_id]["access_token"] == access_token:

                    if request.data:

                        data = request.json

                    else:

                        response["code"] = "EMPTY_REQUEST"

                        response["message"] = "请求体为空"

                        return jsonify(response), 400

                    food_id = data["food_id"]

                    count = data["count"]

                    cursor.execute("select stock from food where id = %s", food_id)

                    result = cursor.fetchall()

                    if result:

                        if count + carts[cart_id]["total"] <= 3:

                            carts[cart_id]["foods"].append(data)

                            carts[cart_id]["total"] += count

                            return jsonify(response), 204

                        else:

                            response["code"] = "FOOD_OUT_OF_LIMIT"

                            response["message"] = "篮子中食物数量超过了三个"

                            return jsonify(response), 403

                    else:

                        response["code"] = "FOOD_NOT_FOUND"

                        response["message"] = "食物不存在"

                        return jsonify(response), 404

                else:

                    response["code"] = "NOT_AUTHORIZED_TO_ACCESS_CART"

                    response["message"] = "无权限访问指定的篮子"

                    return jsonify(response), 401

            else:

                response["code"] = "CART_NOT_FOUND"

                response["message"] = "篮子不存在"

                return jsonify(response), 404

        else:

            response["code"] = "INVALID_ACCESS_TOKEN"

            response["message"] = "无效的令牌"

            return jsonify(response), 401


@app.route("/orders", methods=["POST"])
def gen_order():

    if request.method == "POST":

        response = {}

        access_token = request.args.get("access_token")

        if not access_token:

            access_token = request.headers.get("Access-Token")

        if validate_access_token(access_token):

            if access_tokens[access_token]["ordered"] == 1:

                response["code"] = "ORDER_OUT_OF_LIMIT"

                response["message"] = "每个用户只能下一单"

                return jsonify(response), 403

            if request.data:

                data = request.json

            else:

                response["code"] = "EMPTY_REQUEST"

                response["message"] = "请求体为空"

                return jsonify(response), 400

            cart_id = data["cart_id"]

            if cart_id in carts:

                if carts[cart_id]["access_token"] == access_token:

                    foods = carts[cart_id]["foods"]

                    amount = 0

                    for food in foods:

                        cursor.execute("select stock, price from food where id = %s", food["food_id"])

                        result = cursor.fetchall()[0]

                        stock = result[0]

                        price = result[1]

                        if food["count"] > stock:

                            response["code"] = "FOOD_OUT_OF_STOCK"

                            response["message"] = "食物库存不足"

                            return jsonify(response), 403

                        else:

                            amount += food["count"] * price

                            remain = stock - food["count"]

                            cursor.execute("update food set stock = %s where id = %s", (remain, food["food_id"]))

                            connection.commit()

                    access_tokens[access_token]["ordered"] = 1

                    response = _gen_order(access_token, foods, amount)

                    return jsonify(response), 200

                else:

                    response["code"] = "NOT_AUTHORIZED_TO_ACCESS_CART"

                    response["message"] = "无权限访问指定的篮子"

                    return jsonify(response), 401

            else:

                response["code"] = "CART_NOT_FOUND"

                response["message"] = "篮子不存在"

                return jsonify(response), 404

        else:

            response["code"] = "INVALID_ACCESS_TOKEN"

            response["message"] = "无效的令牌"

            return jsonify(response), 401


@app.route("/orders", methods=["GET"])
def query_orders():

    if request.method == "GET":

        response = {}

        access_token = request.args.get("access_token")

        if not access_token:

            access_token = request.headers.get("Access-Token")

        if validate_access_token(access_token):

            try:

                tmp = orders[access_token]

                tmp.pop("user_id")

                response = [tmp]

            except KeyError:

                return jsonify(response), 200

            return json.dumps(response), 200

        else:

            response["code"] = "INVALID_ACCESS_TOKEN"

            response["message"] = "无效的令牌"

            return jsonify(response), 401


@app.route("/admin/orders", methods=["GET"])
def admin_query_orders():

    if request.method == "GET":

        response = {}

        access_token = request.args.get("access_token")

        if not access_token:

            access_token = request.headers.get("Access-Token")

        if validate_access_token(access_token):

            response = [orders[key] for key in orders.keys()]

            return json.dumps(response), 200

        else:

            response["code"] = "INVALID_ACCESS_TOKEN"

            response["message"] = "无效的令牌"

            return jsonify(response), 401


if __name__ == "__main__":

    # app.run()

    app.run(host="0.0.0.0", port=8080)

    # http = WSGIServer(('', 8080), app)
    #
    # http.serve_forever()


