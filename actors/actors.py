import json

from flask_restful import Resource, Api

from channels import CommandChannel
from codes import SUBMITTED
from models import Actor, Execution, Subscription
from request_utils import RequestParser, APIException, ok
from stores import actors_store, logs_store


class ActorsResource(Resource):

    def get(self):
        return ok(result=[json.loads(actor[1]) for actor in actors_store.items()], msg="Actors retrieved successfully.")

    def validate_post(self):
        parser = RequestParser()
        parser.add_argument('name', type=str, required=True, help="User defined name for this actor.")
        parser.add_argument('image', type=str, required=True,
                            help='Reference to image on docker hub for this actor.')
        parser.add_argument('description', type=str)
        args = parser.parse_args()
        return args

    def post(self):
        args = self.validate_post()
        args['executions'] = {}
        args['state'] = ''
        args['subscriptions'] = []
        args['status'] = SUBMITTED
        actor = Actor(args)
        actors_store[actor.id] = actor.to_db()
        ch = CommandChannel()
        ch.put_cmd(actor_id=actor.id, image=actor.image)
        return ok(result=actor, msg="Actor created successfully.")

    def new_actor_message(self):
        """Put a message on the new_actors queue that actor was created to create a new ActorExecutor for an actor."""
        # TODO
        pass


class ActorResource(Resource):
    def get(self, actor_id):
        try:
            actor = Actor.from_db(actors_store[actor_id])
        except KeyError:
            raise APIException(
                "actor not found: {}'".format(actor_id), 404)
        return ok(result=actor, msg="Actor retrieved successfully.")

    def delete(self, actor_id):
        del actors_store[actor_id]
        self.delete_actor_message(actor_id)
        return ok(result=None, msg='Actor delete successfully.')

    def put(self, actor_id):
        try:
            actor = Actor.from_db(actors_store[actor_id])
        except KeyError:
            raise APIException(
                "actor not found: {}'".format(actor_id), 404)
        args = self.validate_put()
        update_image = False
        args['name'] = actor['name']
        args['id'] = actor['id']
        args['executions'] = actor['executions']
        args['state'] = actor['state']
        if args['image'] == actor.image:
            args['status'] = actor.status
        else:
            update_image = True
            args['status'] = SUBMITTED
        actor = Actor(args)
        actors_store[actor.id] = actor.to_db()
        if update_image:
            ch = CommandChannel()
            ch.put_cmd(actor_id=actor.id, image=actor.image)
        return ok(result=actor, msg="Actor updated successfully.")

    def validate_put(self):
        parser = RequestParser()
        parser.add_argument('image', type=str, required=True,
                            help='Reference to image on docker hub for this actor.')
        parser.add_argument('subscriptions', type=[str], help='List of event ids to subscribe this actor to.')
        parser.add_argument('description', type=str)
        args = parser.parse_args()
        return args

    def delete_actor_message(self, actor_id):
        """Put a command message on the actor_messages queue that actor was deleted."""
        # TODO
        pass


class ActorStateResource(Resource):
    def get(self, actor_id):
        try:
            actor = Actor.from_db(actors_store[actor_id])
            state = actor.get('state')
        except KeyError:
            raise APIException(
                "actor not found: {}'".format(actor_id), 404)
        return ok(result={'state': state }, msg="Actor state retrieved successfully.")

    def post(self, actor_id):
        args = self.validate_post()
        state = args['state']
        try:
            actor = Actor.from_db(actors_store[actor_id])
        except KeyError:
            raise APIException(
                "actor not found: {}'".format(actor_id), 404)
        actor.state = state
        actors_store[actor_id] = actor.to_db()
        return ok(result=actor, msg="State updated successfully.")

    def validate_post(self):
        parser = RequestParser()
        parser.add_argument('state', type=str, required=True, help="Set the state for this actor.")
        args = parser.parse_args()
        return args


class ActorSubscriptionResource(Resource):
    def get(self, actor_id):
        try:
            actor = Actor.from_db(actors_store[actor_id])
            subscriptions = actor.get('subscriptions') or {'subscriptions': None}
        except KeyError:
            raise APIException(
                "actor not found: {}'".format(actor_id), 404)
        return ok(result=subscriptions, msg="Subscriptions retrieved successfully.")

    def post(self, actor_id):
        args = self.validate_post()
        try:
            actor = Actor.from_db(actors_store[actor_id])
        except KeyError:
            raise APIException(
                "actor not found: {}'".format(actor_id), 404)
        event_ids = args['event_id']
        event_patterns = args['event_pattern']
        subs = {}
        for id in event_ids:
            s = Subscription(actor, {'event_id': id})
            subs[s.id] = s
            actor.subscriptions = subs
        for pat in event_patterns:
            s = Subscription(actor, {'event_pattern': pat})
            subs[s.id] = s
            actor.subscriptions = subs
        actors_store[actor_id] = actor.to_db()
        return ok(result=actor, msg="Subscriptions updated successfully.")

    def validate_post(self):
        parser = RequestParser()
        parser.add_argument('event_id', type=str, action='append', help="Event id for the subscription.")
        parser.add_argument('event_pattern', type=str, action='append', help="Regex pattern of event id's for the subscription.")
        args = parser.parse_args()
        return args


class ActorExecutionsResource(Resource):
    def get(self, actor_id):
        try:
            actor = Actor.from_db(actors_store[actor_id])
        except KeyError:
            raise APIException(
                "actor not found: {}'".format(actor_id), 404)
        tot = {'total_executions': 0, 'total_cpu': 0, 'total_io':0, 'total_runtime': 0, 'ids':[]}
        executions = actor.get('executions') or {}
        for id, val in executions.items():
            tot['ids'].append(id)
            tot['total_executions'] += 1
            tot['total_cpu'] += int(val['cpu'])
            tot['total_io'] += int(val['io'])
            tot['total_runtime'] += int(val['runtime'])
        return ok(result=tot, msg="Actor executions retrieved successfully.")

    def post(self, actor_id):
        try:
            actor = Actor.from_db(actors_store[actor_id])
        except KeyError:
            raise APIException(
                "actor not found: {}'".format(actor_id), 404)
        args = self.validate_post()
        Execution.add_execution(actor_id, args)
        return ok(result=actor, msg="Actor execution added successfully.")

    def validate_post(self):
        parser = RequestParser()
        parser.add_argument('runtime', type=str, required=True, help="Runtime, in milliseconds, of the execution.")
        parser.add_argument('cpu', type=str, required=True, help="CPU usage, in user jiffies, of the execution.")
        parser.add_argument('io', type=str, required=True, help="Block I/O usage, in number of 512-byte sectors read from and written to, by the execution.")
        # Accounting for memory is quite hard -- probably easier to cap all containers at a fixed amount or perhaps have a graduated
        # list of cap sized (e.g. small, medium and large).
        # parser.add_argument('mem', type=str, required=True, help="Memory usage, , of the execution.")
        args = parser.parse_args()
        for k,v in args.items():
            try:
                int(v)
            except ValueError:
                raise APIException(message="Argument " + k + " must be an integer.")
        return args


class ActorExecutionResource(Resource):
    def get(self, actor_id, execution_id):
        try:
            actor = Actor.from_db(actors_store[actor_id])
        except KeyError:
            raise APIException(
                "actor not found: {}'".format(actor_id), 404)
        try:
            excs = actor.executions
        except KeyError:
            raise APIException("No executions found for actor {}.".format(actor_id))
        try:
            exc = excs[execution_id]
        except KeyError:
            raise APIException("Execution not found {}.".format(execution_id))
        return ok(result=exc, msg="Actor execution retrieved successfully.")

class ActorExecutionLogsResource(Resource):
    def get(self, actor_id, execution_id):
        try:
            actor = Actor.from_db(actors_store[actor_id])
        except KeyError:
            raise APIException(
                "actor not found: {}'".format(actor_id), 404)
        try:
            excs = actor.executions
        except KeyError:
            raise APIException("No executions found for actor {}.".format(actor_id))
        try:
            logs = logs_store[execution_id]
        except KeyError:
            logs = ""
        return ok(result=logs, msg="Logs retrieved successfully.")
