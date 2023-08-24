"""
Discussion notifications sender util.
"""
from openedx_events.learning.signals import USER_NOTIFICATION_REQUESTED
from openedx_events.learning.data import UserNotificationData
from openedx.core.djangoapps.django_comment_common.comment_client.comment import Comment
from django.conf import settings

from openedx.core.djangoapps.django_comment_common.comment_client.subscriptions import Subscription


def send_response_notifications(thread, course, creator, parent_id=None):
    """
    Send notifications to users who are subscribed to the thread.
    """
    notification_sender = DiscussionNotificationSender(thread, course, creator, parent_id)
    notification_sender.send_new_comment_notification()
    notification_sender.send_new_response_notification()
    notification_sender.send_new_comment_on_response_notification()
    notification_sender.send_response_on_followed_post_notification()


class DiscussionNotificationSender:
    """
    Class to send notifications to users who are subscribed to the thread.
    """

    def __init__(self, thread, course, creator, parent_id=None):
        self.thread = thread
        self.course = course
        self.creator = creator
        self.parent_id = parent_id
        self.parent_response = None
        self._get_parent_response()

    def _send_notification(self, user_ids, notification_type, extra_context=None):
        """
        Send notification to users
        """
        if not user_ids:
            return

        if extra_context is None:
            extra_context = {}

        notification_data = UserNotificationData(
            user_ids=[int(user_id) for user_id in user_ids],
            context={
                "replier_name": self.creator.username,
                "post_title": self.thread.title,
                "course_name": self.course.display_name,
                **extra_context,
            },
            notification_type=notification_type,
            content_url=f"{settings.DISCUSSIONS_MICROFRONTEND_URL}/{str(self.course.id)}/posts/{self.thread.id}",
            app_name="discussion",
            course_key=self.course.id,
        )
        USER_NOTIFICATION_REQUESTED.send_event(notification_data=notification_data)

    def _get_parent_response(self):
        """
        Get parent response object
        """
        if self.parent_id and not self.parent_response:
            self.parent_response = Comment(id=self.parent_id).retrieve()

        return self.parent_response

    def send_new_response_notification(self):
        """
        Send notification to users who are subscribed to the main thread/post i.e.
        there is a response to the main thread.
        """
        if not self.parent_id and self.creator.id != int(self.thread.user_id):
            self._send_notification([self.thread.user_id], "new_response")

    def _response_and_thread_has_same_creator(self) -> bool:
        """
        Check if response and main thread have same author.
        """
        return int(self.parent_response.user_id) == int(self.thread.user_id)

    def send_new_comment_notification(self):
        """
        Send notification to parent thread creator i.e. comment on the response.
        """
        #
        if (
            self.parent_response and
            self.creator.id != int(self.thread.user_id)
        ):
            # use your if author of response is same as author of post.
            author_name = "your" if self._response_and_thread_has_same_creator() else self.parent_response.username
            context = {
                "author_name": author_name,
            }
            self._send_notification([self.thread.user_id], "new_comment", extra_context=context)

    def send_new_comment_on_response_notification(self):
        """
        Send notification to parent response creator i.e. comment on the response.
        Do not send notification if author of response is same as author of post.
        """
        if (
            self.parent_response and
            self.creator.id != int(self.parent_response.user_id) and not
            self._response_and_thread_has_same_creator()
        ):
            self._send_notification([self.parent_response.user_id], "new_comment_on_response")

    def send_response_on_followed_post_notification(self):
        """
        Send notification to followers of the thread/post
        except:
        Tread creator , response creator,
        """
        users = []
        page = 1
        has_more_subscribers = True

        while has_more_subscribers:

            subscribers = Subscription.get(self.thread.id, query_params={'page': page})
            if page <= subscribers.num_pages:
                for subscriber in subscribers.collection:
                    # Check if the subscriber is not the thread creator or response creator
                    subscriber_id = int(subscriber.get('subscriber_id'))
                    # do not send notification to the user who created the response and the thread
                    if subscriber_id != int(self.thread.user_id) and subscriber_id != int(self.creator.id):
                        users.append(subscriber_id)
            else:
                has_more_subscribers = False
            page += 1
        # Remove duplicate users from the list of users to send notification
        users = list(set(users))
        if not self.parent_id:
            self._send_notification(users, "response_on_followed_post")
        else:
            self._send_notification(
                users,
                "comment_on_followed_post",
                extra_context={"author_name": self.parent_response.username}
            )
