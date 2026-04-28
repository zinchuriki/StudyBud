from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from base.models import Message, Room, Topic


User = get_user_model()


class BaseTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alice",
            email="alice@example.com",
            password="testpass123",
            name="Alice",
        )
        self.other_user = User.objects.create_user(
            username="bob",
            email="bob@example.com",
            password="testpass123",
            name="Bob",
        )
        self.python = Topic.objects.create(name="Python")
        self.javascript = Topic.objects.create(name="JavaScript")
        self.python_room = Room.objects.create(
            host=self.user,
            topic=self.python,
            name="Django study group",
            description="Learn views and models",
        )
        self.javascript_room = Room.objects.create(
            host=self.other_user,
            topic=self.javascript,
            name="Frontend practice",
            description="Learn components",
        )


class ModelTests(BaseTestCase):
    def test_model_string_representations(self):
        message = Message.objects.create(
            user=self.user,
            room=self.python_room,
            body="This is a useful message about Django testing.",
        )

        self.assertEqual(str(self.python), "Python")
        self.assertEqual(str(self.python_room), "Django study group")
        self.assertEqual(str(message), "This is a useful message about Django testing.")

    def test_message_string_is_truncated_to_50_characters(self):
        body = "x" * 70
        message = Message.objects.create(
            user=self.user,
            room=self.python_room,
            body=body,
        )

        self.assertEqual(str(message), body[:50])


class RoomViewTests(BaseTestCase):
    def test_home_lists_rooms_and_filters_by_query(self):
        response = self.client.get(reverse("home"), {"q": "python"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Django study group")
        self.assertNotContains(response, "Frontend practice")
        self.assertEqual(response.context["room_count"], 1)
        self.assertQuerySetEqual(
            response.context["rooms"],
            [self.python_room],
            transform=lambda room: room,
        )

    def test_room_detail_shows_messages_and_participants(self):
        self.python_room.participants.add(self.user)
        message = Message.objects.create(
            user=self.user,
            room=self.python_room,
            body="Hello from a test message",
        )

        response = self.client.get(reverse("room", args=[self.python_room.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Django study group")
        self.assertContains(response, message.body)
        self.assertIn(self.user, response.context["participants"])

    def test_authenticated_user_can_post_message_to_room(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("room", args=[self.python_room.id]),
            {"body": "Count me in"},
        )

        self.assertRedirects(response, reverse("room", args=[self.python_room.id]))
        message = Message.objects.get(body="Count me in")
        self.assertEqual(message.user, self.user)
        self.assertEqual(message.room, self.python_room)
        self.assertIn(self.user, self.python_room.participants.all())

    def test_create_room_requires_login(self):
        response = self.client.get(reverse("create-room"))

        self.assertRedirects(response, f'{reverse("login")}?next={reverse("create-room")}')

    def test_authenticated_user_can_create_room_with_new_topic(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("create-room"),
            {
                "topic": "Databases",
                "name": "SQL practice",
                "description": "Indexes and joins",
            },
        )

        self.assertRedirects(response, reverse("home"))
        room = Room.objects.get(name="SQL practice")
        self.assertEqual(room.host, self.user)
        self.assertEqual(room.topic.name, "Databases")
        self.assertEqual(room.description, "Indexes and joins")

    def test_only_host_can_update_room(self):
        self.client.force_login(self.other_user)

        response = self.client.post(
            reverse("update-room", args=[self.python_room.id]),
            {
                "topic": "Security",
                "name": "Changed by non-host",
                "description": "This should not persist",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.python_room.refresh_from_db()
        self.assertEqual(self.python_room.name, "Django study group")
        self.assertEqual(self.python_room.topic, self.python)

    def test_host_can_update_room(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("update-room", args=[self.python_room.id]),
            {
                "topic": "Django",
                "name": "Updated study group",
                "description": "Forms and views",
            },
        )

        self.assertRedirects(response, reverse("home"))
        self.python_room.refresh_from_db()
        self.assertEqual(self.python_room.name, "Updated study group")
        self.assertEqual(self.python_room.topic.name, "Django")
        self.assertEqual(self.python_room.description, "Forms and views")

    def test_only_host_can_delete_room(self):
        self.client.force_login(self.other_user)

        response = self.client.post(reverse("delete-room", args=[self.python_room.id]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Room.objects.filter(id=self.python_room.id).exists())

    def test_host_can_delete_room(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("delete-room", args=[self.python_room.id]))

        self.assertRedirects(response, reverse("home"))
        self.assertFalse(Room.objects.filter(id=self.python_room.id).exists())


class MessageViewTests(BaseTestCase):
    def test_only_message_author_can_delete_message(self):
        message = Message.objects.create(
            user=self.user,
            room=self.python_room,
            body="Keep this message",
        )
        self.client.force_login(self.other_user)

        response = self.client.post(reverse("delete-message", args=[message.id]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Message.objects.filter(id=message.id).exists())

    def test_message_author_can_delete_message(self):
        message = Message.objects.create(
            user=self.user,
            room=self.python_room,
            body="Delete this message",
        )
        self.client.force_login(self.user)

        response = self.client.post(reverse("delete-message", args=[message.id]))

        self.assertRedirects(response, reverse("home"))
        self.assertFalse(Message.objects.filter(id=message.id).exists())


class AuthViewTests(BaseTestCase):
    def test_login_page_authenticates_with_email(self):
        response = self.client.post(
            reverse("login"),
            {
                "email": "alice@example.com",
                "password": "testpass123",
            },
        )

        self.assertRedirects(response, reverse("home"))

    def test_authenticated_user_is_redirected_from_login_page(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("login"))

        self.assertRedirects(response, reverse("home"))

    def test_logout_redirects_home(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("logout"))

        self.assertRedirects(response, reverse("home"))


class TopicAndActivityViewTests(BaseTestCase):
    def test_topics_page_filters_topics_by_query(self):
        response = self.client.get(reverse("topics"), {"q": "java"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "JavaScript")
        self.assertNotContains(response, "Python")

    def test_activity_page_lists_messages(self):
        message = Message.objects.create(
            user=self.user,
            room=self.python_room,
            body="Recent activity message",
        )

        response = self.client.get(reverse("activity"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, message.body)
